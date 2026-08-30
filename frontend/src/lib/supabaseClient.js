import { createClient } from '@supabase/supabase-js';

const url = process.env.REACT_APP_SUPABASE_URL;
const anonKey = process.env.REACT_APP_SUPABASE_ANON_KEY;

if (!url || !anonKey) {
  // Keep local development explicit without exposing server credentials.
  console.warn('Supabase frontend environment is not configured.');
}

export const supabase = createClient(url || 'https://invalid.local', anonKey || 'invalid-anon-key', {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
});
