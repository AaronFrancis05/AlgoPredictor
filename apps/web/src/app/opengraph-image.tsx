import { ImageResponse } from "next/og";

import { site } from "@/lib/site";

export const alt = `${site.name} | ${site.tagline}`;
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpenGraphImage() {
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", justifyContent: "center",
                    padding: 80, background: "#0b0f14", color: "#e7edf5" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 20, fontSize: 40, fontWeight: 800 }}>
          <div style={{ display: "flex", width: 72, height: 72, borderRadius: 6, background: "#22c55e", color: "#04130a",
                        alignItems: "center", justifyContent: "center" }}>AP</div>
          {site.name}
        </div>
        <div style={{ marginTop: 40, fontSize: 64, fontWeight: 800, lineHeight: 1.1 }}>
          Know what to back before kick-off.
        </div>
        <div style={{ marginTop: 30, fontSize: 30, color: "#93a1b5" }}>
          Today&apos;s strongest picks · slips at your odds · every result public · 18+
        </div>
      </div>
    ),
    size,
  );
}
