export default async function handler(request) {
  // Proxy to Palmeiras Data API calendar endpoint
  const DATA_API = 'https://palmeiras-data.vercel.app';
  
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    
    const resp = await fetch(`${DATA_API}/api/calendar.ics`, {
      signal: controller.signal
    });
    clearTimeout(timeout);
    
    if (!resp.ok) {
      return new Response(`Error: ${resp.status}`, { status: resp.status });
    }
    
    const ics = await resp.text();
    
    return new Response(ics, {
      status: 200,
      headers: {
        'Content-Type': 'text/calendar',
        'Cache-Control': 'public, max-age=3600',
      },
    });
    
  } catch (error) {
    return new Response(`Error: ${error.message}`, { status: 500 });
  }
}
