-- Migration: Advanced Search RPC with Ranking
-- This function implements weighted search: Title (A) > Category (B) > Tags (C) > Description (D)

-- Drop function if exists to allow updates
DROP FUNCTION IF EXISTS search_tests_ranked;

CREATE OR REPLACE FUNCTION search_tests_ranked(
    search_query text,
    limit_count int DEFAULT 50,
    offset_count int DEFAULT 0,
    min_match_score float DEFAULT 0.1,
    creator_filter uuid DEFAULT NULL
)
RETURNS TABLE (
    id uuid,
    title text,
    description text,
    custom_id text,
    slug text,
    cover_image text,
    total_questions int,
    duration int,
    test_type text,
    difficulty text,
    created_at timestamptz,
    created_by uuid,
    visibility text,
    is_public boolean,
    match_score float,
    match_type text
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH scored_tests AS (
        SELECT
            t.id,
            t.title,
            t.description,
            t.custom_id,
            t.slug,
            t.cover_image,
            t.total_questions,
            t.duration,
            t.test_type,
            t.difficulty,
            t.created_at,
            t.created_by,
            t.visibility,
            t.is_public,
            -- Calculate score based on where match was found
            CASE
                -- Exact Title/ID Match (Highest Priority)
                WHEN t.title ILIKE search_query OR t.custom_id ILIKE search_query
                THEN 1.0

                -- Title/ID Contains Match
                WHEN t.title ILIKE '%' || search_query || '%' OR t.custom_id ILIKE '%' || search_query || '%'
                THEN 0.8

                -- Category Match
                WHEN EXISTS (
                    SELECT 1 FROM test_categories tc
                    JOIN categories c ON c.id = tc.category_id
                    WHERE tc.test_id = t.id AND c.name ILIKE '%' || search_query || '%'
                ) THEN 0.6

                -- Tag Match
                WHEN EXISTS (
                    SELECT 1 FROM unnest(t.tags) AS tag
                    WHERE tag ILIKE '%' || search_query || '%'
                ) THEN 0.5

                -- Description Match (Lowest Priority)
                WHEN t.description ILIKE '%' || search_query || '%'
                THEN 0.3

                ELSE 0.0
            END as match_score,
            CASE
                WHEN t.title ILIKE '%' || search_query || '%' THEN 'Title'
                WHEN EXISTS (SELECT 1 FROM test_categories tc JOIN categories c ON tc.category_id=c.id WHERE tc.test_id=t.id AND c.name ILIKE '%'||search_query||'%') THEN 'Category'
                WHEN EXISTS (SELECT 1 FROM unnest(t.tags) tag WHERE tag ILIKE '%'||search_query||'%') THEN 'Tag'
                ELSE 'Description'
            END as match_type
        FROM tests t
        WHERE
            (
                (creator_filter IS NOT NULL AND t.created_by = creator_filter)
                OR
                (creator_filter IS NULL AND (t.is_public = true OR EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.is_admin = true)))
            )
    )
    SELECT
        st.id,
        st.title,
        st.description,
        st.custom_id,
        st.slug,
        st.cover_image,
        st.total_questions,
        st.duration,
        st.test_type,
        st.difficulty,
        st.created_at,
        st.created_by,
        st.visibility,
        st.is_public,
        st.match_score,
        st.match_type
    FROM scored_tests st
    WHERE st.match_score >= min_match_score
    ORDER BY st.match_score DESC, st.created_at DESC
    LIMIT limit_count OFFSET offset_count;
END;
$$;
