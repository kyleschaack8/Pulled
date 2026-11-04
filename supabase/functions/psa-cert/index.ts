// Pulled: look up a PSA cert number (Supabase Edge Function "psa-cert").
// The PSA token stays here as a secret (PSA_TOKEN) and never reaches the website.
// Only signed-in members can use it. Each cert is saved in psa_certs and reused,
// and lookups stop at DAILY_LIMIT per 24 hours to stay inside PSA's free allowance.
import { createClient } from 'npm:@supabase/supabase-js@2.117.3';

const DAILY_LIMIT = 90;
const FRESH_DAYS = 30;
const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
};
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...CORS, 'Content-Type': 'application/json' } });
const KEEP = ['CertNumber', 'SpecID', 'Year', 'Brand', 'Category', 'CardNumber', 'Subject', 'Variety', 'GradeDescription', 'CardGrade', 'TotalPopulation', 'PopulationHigher', 'LabelType', 'IsDualCert', 'ItemStatus'];

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: CORS });
  if (req.method !== 'POST') return json({ error: 'method' }, 405);

  const admin = createClient(Deno.env.get('SUPABASE_URL')!, Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!, { auth: { persistSession: false } });

  // signed-in members only
  const jwt = (req.headers.get('Authorization') || '').replace(/^Bearer\s+/i, '');
  const who = jwt ? await admin.auth.getUser(jwt) : null;
  const user = who && who.data && who.data.user;
  if (!user) return json({ error: 'signin' }, 401);

  let cert = '';
  try { cert = String((await req.json()).cert || '').replace(/\D/g, ''); } catch (_) { /* bad body */ }
  if (!/^\d{6,10}$/.test(cert)) return json({ error: 'cert' }, 400);

  // saved lookup?
  const saved = await admin.from('psa_certs').select('cert,found,data,fetched_at').eq('cert', cert).maybeSingle();
  const hit = saved.data;
  if (hit && Date.now() - Date.parse(hit.fetched_at) < FRESH_DAYS * 864e5) return json({ cert, found: hit.found, data: hit.data, saved: true });

  // daily allowance
  const since = new Date(Date.now() - 864e5).toISOString();
  const used = await admin.from('psa_certs').select('cert', { count: 'exact', head: true }).gte('fetched_at', since);
  if ((used.count ?? 0) >= DAILY_LIMIT) return hit ? json({ cert, found: hit.found, data: hit.data, saved: true }) : json({ error: 'limit' }, 429);

  // tolerate stray spaces, quotes or a pasted "bearer " in the secret
  const token = (Deno.env.get('PSA_TOKEN') || '').trim().replace(/^bearer\s+/i, '').replace(/^["']+|["']+$/g, '').trim();
  if (!token) return json({ error: 'setup' }, 500);

  let res: Response;
  try {
    res = await fetch('https://api.psacard.com/publicapi/cert/GetByCertNumber/' + cert, {
      headers: { Authorization: 'bearer ' + token, Accept: 'application/json', 'User-Agent': 'Pulled/1.0 (sports card tracker; +https://kyleschaack8.github.io/Pulled/)' },
    });
  } catch (e) {
    console.log('PSA request failed:', String(e));
    return json({ error: 'psa' }, 502);
  }
  let body: any = null;
  try { body = await res.json(); } catch (_) { /* not json */ }
  const c = body && body.PSACert;
  if (!c) console.log('PSA replied', res.status, JSON.stringify(body).slice(0, 300), '| token length', token.length);
  if (res.status === 429) return json({ error: 'limit', psaStatus: 429 }, 429);
  if (res.status === 401 || res.status === 403 || (res.status >= 500 && !c)) return json({ error: 'token', psaStatus: res.status }, 502);
  if (!res.ok && res.status !== 404 && !c) return json({ error: 'psa', psaStatus: res.status }, 502);

  const found = !!(c && c.CertNumber);
  const data = found ? Object.fromEntries(KEEP.filter((k) => c[k] !== undefined && c[k] !== null).map((k) => [k, typeof c[k] === 'string' ? c[k].slice(0, 120) : c[k]])) : null;
  await admin.from('psa_certs').upsert({ cert, found, data, fetched_at: new Date().toISOString(), checked_by: user.id });
  return json({ cert, found, data });
});
