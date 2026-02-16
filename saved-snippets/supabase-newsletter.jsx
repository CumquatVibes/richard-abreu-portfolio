// SAVED FOR LATER — Supabase Newsletter Subscriber System
// Use when/if we migrate to Next.js

// ============================================
// 1. SQL — Run in Supabase SQL Editor
// ============================================
/*
create table newsletter_subscribers (
  id uuid default uuid_generate_v4() primary key,
  email text unique not null,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,
  status text default 'active' -- active, unsubscribed
);

alter table newsletter_subscribers enable row level security;

create policy "Enable insert for authenticated users only"
on newsletter_subscribers for insert
with check (true);
*/

// ============================================
// 2. React Component
// ============================================
import { useState } from 'react';
import { createClient } from '@supabase/supabase-js';

const supabase = createClient(process.env.NEXT_PUBLIC_SUPABASE_URL, process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY);

export default function NewsletterSignup() {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  const handleSubscribe = async (e) => {
    e.preventDefault();
    setLoading(true);

    const { error } = await supabase
      .from('newsletter_subscribers')
      .insert([{ email }]);

    if (error) {
      setMessage("Check your email, looks like you might already be on the list!");
    } else {
      setMessage("You're in. Welcome to the Studio Signal.");
      setEmail('');
    }
    setLoading(false);
  };

  return (
    <div className="max-w-md mx-auto p-8 bg-white border-2 border-[#00ced1] rounded-lg shadow-[8px_8px_0px_0px_rgba(0,206,209,1)]">
      <h2 className="text-2xl font-bold text-gray-900 mb-2 uppercase tracking-tight">Join the Studio Signal</h2>
      <p className="text-gray-600 mb-6">Navy-grade systems, automation deep-dives, and creative intel. Straight to your inbox.</p>

      <form onSubmit={handleSubscribe} className="space-y-4">
        <input
          type="email"
          placeholder="your@email.com"
          required
          className="w-full px-4 py-3 border-2 border-gray-200 rounded focus:border-[#00ced1] outline-none transition-all"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <button
          type="submit"
          disabled={loading}
          className="w-full bg-[#00ced1] hover:bg-[#008b8b] text-white font-bold py-3 px-6 rounded transition-colors uppercase tracking-widest text-sm"
        >
          {loading ? 'Sinking anchor...' : 'Get the Signal'}
        </button>
      </form>
      {message && <p className="mt-4 text-sm font-medium text-[#008b8b] animate-pulse">{message}</p>}
    </div>
  );
}
