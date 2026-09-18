import type { MetadataRoute } from "next";

import { site } from "@/lib/site";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: site.name,
    short_name: site.name,
    description: site.description,
    start_url: "/dashboard",
    display: "standalone",
    background_color: "#0b0f14",
    theme_color: "#22c55e",
    icons: [{ src: "/icon", sizes: "64x64", type: "image/png" }],
  };
}
