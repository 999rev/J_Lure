const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Accept",
};

export async function onRequest(context) {
  const { request } = context;
  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: CORS_HEADERS });
  }

  const reqUrl = new URL(request.url);

  // 1. Overpass 河道地形请求转发
  if (reqUrl.searchParams.get("target") === "overpass" || request.method === "POST") {
    const bodyText = await request.text();
    const endpoints = [
      "https://overpass-api.de/api/interpreter",
      "https://overpass.kumi.systems/api/interpreter",
      "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    ];
    for (const ep of endpoints) {
      try {
        const resp = await fetch(ep, {
          method: "POST",
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "castwindow-pages/1.0",
          },
          body: bodyText,
        });
        if (!resp.ok) continue;
        const data = await resp.text();
        return new Response(data, {
          status: 200,
          headers: {
            ...CORS_HEADERS,
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "public, max-age=3600",
          },
        });
      } catch (_) {}
    }
    return new Response(JSON.stringify({ error: "All Overpass mirrors failed" }), {
      status: 502,
      headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  }

  // 2. Open-Meteo 未来 72h 气象预报转发（保证深夜也能截取完整 48h）
  const lat = reqUrl.searchParams.get("latitude") || "22.8170";
  const lon = reqUrl.searchParams.get("longitude") || "108.3665";
  const upstream = new URL("https://api.open-meteo.com/v1/forecast");
  upstream.searchParams.set("latitude", lat);
  upstream.searchParams.set("longitude", lon);
  upstream.searchParams.set(
    "hourly",
    "temperature_2m,surface_pressure,wind_speed_10m,wind_direction_10m,cloud_cover,precipitation_probability"
  );
  upstream.searchParams.set("past_days", "1");
  upstream.searchParams.set("forecast_days", "3");
  upstream.searchParams.set("timezone", "auto");

  try {
    const resp = await fetch(upstream.toString());
    const body = await resp.text();
    return new Response(body, {
      status: resp.status,
      headers: {
        ...CORS_HEADERS,
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "public, max-age=900",
      },
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: String(err) }), {
      status: 502,
      headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  }
}
