// ---------------------------------------------------------------------------
// Members-only for a bzhmacro.com site on Vercel. One file, no dependencies:
// put it in the project's root directory (next to package.json / index.html)
// and push. Delete it to make the site public again.
//
// Every page then checks with account.bzhmacro.com first:
//   not signed in        → Google sign-in, then straight back here
//   signed in, no access → "members only" page; the request shows on the
//                          dashboard, where one click lets them in
//   member or admin      → the page, as normal (and the visit is recorded)
// If the hub can't be reached the site stays shut rather than open.
//
// Images, fonts, stylesheets and script bundles skip the check (they're not
// the content, and checking each would slow every page). Pages, JSON and CSV
// data stay behind it. Source: github.com/bzhmacro/bzhmacro-account/drop-in
// ---------------------------------------------------------------------------

const HUB = 'https://account.bzhmacro.com';

// Paths that must stay reachable without a person signed in — e.g. a
// Vercel cron endpoint. Add prefixes here if the site has any.
const OPEN_PATHS = [];

export const config = {
  matcher: ['/((?!.*\\.(?:png|jpe?g|gif|webp|avif|svg|ico|woff2?|ttf|otf|css|js|mjs|map|webmanifest|txt|xml)$).*)'],
};

export default async function middleware(request) {
  return (await gate(request)) || pass();
}

/** Carry on to the page (what @vercel/functions' next() does). */
const pass = () => new Response(null, { headers: { 'x-middleware-next': '1' } });

export async function gate(request, { hub = HUB, fetchImpl = fetch, timeoutMs = 4000, open = OPEN_PATHS } = {}) {
  const url = new URL(request.url);
  if (open.some(p => url.pathname.startsWith(p))) return null;
  const back = encodeURIComponent(url.href);
  const isPage = request.headers.get('sec-fetch-dest') === 'document'
    || (request.headers.get('accept') || '').includes('text/html');
  const q = new URLSearchParams({ site: url.host, path: url.pathname + url.search, page: isPage ? '1' : '0' });
  const ref = request.headers.get('referer');
  if (isPage && ref) q.set('ref', ref.slice(0, 500));

  let res = null;
  try {
    res = await fetchImpl(`${hub}/api/gate?${q}`, {
      headers: { cookie: request.headers.get('cookie') || '' },
      signal: AbortSignal.timeout(timeoutMs),
      cache: 'no-store',
    });
  } catch { /* unreachable: handled below */ }

  if (res && res.status === 200) return null;
  if (res && res.status === 401) return redirect(`${hub}/sign-in?next=${back}`);
  if (res && res.status === 403) return redirect(`${hub}/denied?next=${back}`);
  return new Response('Members-only site: the sign-in service is unreachable. Try again shortly.', {
    status: 503,
    headers: { 'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'no-store', 'Retry-After': '30' },
  });
}

const redirect = to => new Response(null, { status: 302, headers: { Location: to, 'Cache-Control': 'no-store' } });
