-- Enable Row Level Security
ALTER TABLE public.tests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.classes ENABLE ROW LEVEL SECURITY;

-- 1. Helper Function to check admin status via email
CREATE OR REPLACE FUNCTION public.is_admin()
RETURNS BOOLEAN AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM public.admins 
    WHERE email = auth.jwt() ->> 'email'
  );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 2. Tests Policy for Admins
DROP POLICY IF EXISTS "Enable all access for admins" ON public.tests;
CREATE POLICY "Enable all access for admins"
ON public.tests
FOR ALL
TO authenticated
USING ( public.is_admin() )
WITH CHECK ( public.is_admin() );

-- 3. Categories Policy for Admins
DROP POLICY IF EXISTS "Enable all access for admins" ON public.categories;
CREATE POLICY "Enable all access for admins"
ON public.categories
FOR ALL
TO authenticated
USING ( public.is_admin() )
WITH CHECK ( public.is_admin() );

-- 4. Classes Policy for Admins
DROP POLICY IF EXISTS "Enable all access for admins" ON public.classes;
CREATE POLICY "Enable all access for admins"
ON public.classes
FOR ALL
TO authenticated
USING ( public.is_admin() )
WITH CHECK ( public.is_admin() );

-- Note: Ensure existing policies for creators/public still exist. 
-- Policies are additive (OR logic), so adding this policy grants admin access without removing others.
