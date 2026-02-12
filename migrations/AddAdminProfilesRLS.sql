-- Enable RLS on profiles (likely already enabled, but safe to repeat)
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

-- Policy for Admins to manage profiles
DROP POLICY IF EXISTS "Enable all access for admins" ON public.profiles;

CREATE POLICY "Enable all access for admins"
ON public.profiles
FOR ALL
TO authenticated
USING ( public.is_admin() )
WITH CHECK ( public.is_admin() );
