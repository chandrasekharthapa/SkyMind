"use client";

import { useEffect, useRef } from "react";

/*
 * Hero background: planes flying between the airports SkyMind tracks, drawn on
 * a canvas. The routes are the ones in backend/route_catalog/routes.yaml, so
 * the animation shows the real network.
 *
 * Drawn in code rather than played from a video: nothing to download, sharp
 * at any size, and it follows the theme's accent colour. It pauses when the
 * hero is off screen or the tab is hidden, and draws a single still frame for
 * people who ask for reduced motion.
 */

// Airport positions as [longitude, latitude].
const AIRPORTS: Record<string, [number, number]> = {
  DEL: [77.10, 28.56], BOM: [72.87, 19.09], BLR: [77.71, 13.20], HYD: [78.43, 17.24],
  MAA: [80.17, 12.99], CCU: [88.45, 22.65], AMD: [72.63, 23.07], COK: [76.40, 10.15],
  GOI: [73.83, 15.38], PNQ: [73.92, 18.58], IXC: [76.79, 30.67], BBI: [85.82, 20.25],
  TRV: [76.92, 8.48], VTZ: [83.22, 17.72],
};

// One direction of each tracked route; planes fly both ways.
const ROUTES: [string, string][] = [
  ["DEL", "BOM"], ["DEL", "BLR"], ["DEL", "HYD"], ["DEL", "MAA"], ["DEL", "CCU"],
  ["DEL", "BBI"], ["BBI", "BOM"], ["BBI", "BLR"], ["BOM", "BLR"], ["BOM", "HYD"],
  ["BOM", "MAA"], ["BOM", "CCU"], ["BLR", "HYD"], ["BLR", "MAA"], ["BLR", "CCU"],
  ["DEL", "AMD"], ["DEL", "GOI"], ["DEL", "COK"], ["DEL", "PNQ"], ["DEL", "IXC"],
  ["BOM", "GOI"], ["BOM", "AMD"], ["BLR", "COK"], ["BLR", "GOI"], ["HYD", "MAA"],
  ["HYD", "CCU"], ["DEL", "VTZ"], ["BOM", "TRV"],
];

// Bounds of the airports, used to spread the network across the whole hero.
// The x and y axes are scaled separately so the routes fill a wide screen;
// north stays up and relative positions are right, but distances are not to
// scale, which is why no country outline is drawn.
const LON_MIN = 72.4, LON_MAX = 88.7, LAT_MIN = 8.3, LAT_MAX = 30.9;
const MAX_FLIGHTS = 14;
const TRAIL = 0.22; // fraction of the route the glowing trail covers

type Pt = { x: number; y: number };
type Flight = { from: string; to: string; start: number; duration: number };

function bezier(a: Pt, c: Pt, b: Pt, t: number): Pt {
  const u = 1 - t;
  return { x: u * u * a.x + 2 * u * t * c.x + t * t * b.x, y: u * u * a.y + 2 * u * t * c.y + t * t * b.y };
}

export default function FlightNetwork({ className }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const readAccent = () => getComputedStyle(document.documentElement).getPropertyValue("--red").trim() || "#e03131";
    let accent = readAccent();
    // Follow the light/dark toggle, which changes the accent colour.
    const themeObserver = new MutationObserver(() => {
      accent = readAccent();
      if (!running) draw(performance.now());
    });
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "class"] });

    let width = 0, height = 0, dpr = 1;
    let project = (lon: number, lat: number): Pt => ({ x: lon, y: lat });
    const arrivals: Record<string, number> = {};
    const flights: Flight[] = [];
    let raf = 0;
    let running = false;
    let visible = true;

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      width = rect.width;
      height = rect.height;
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      // Spread the airports over the hero, clear of the fixed nav bar.
      const narrow = width < 900;
      const padX = width * (narrow ? 0.1 : 0.07);
      const top = narrow ? 100 : 130;
      const bottom = narrow ? 40 : 70;
      project = (lon, lat) => ({
        x: padX + ((lon - LON_MIN) / (LON_MAX - LON_MIN)) * (width - 2 * padX),
        y: top + ((LAT_MAX - lat) / (LAT_MAX - LAT_MIN)) * (height - top - bottom),
      });
    };

    const control = (a: Pt, b: Pt): Pt => {
      const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
      const dx = b.x - a.x, dy = b.y - a.y;
      // Bow every arc to the same side of its direction of travel, so the
      // outbound and return legs of a route draw as two separate curves.
      return { x: mx - dy * 0.18, y: my + dx * 0.18 };
    };

    const spawn = (now: number, stagger = 0) => {
      const [p, q] = ROUTES[Math.floor(Math.random() * ROUTES.length)];
      const [from, to] = Math.random() < 0.5 ? [p, q] : [q, p];
      const a = project(...AIRPORTS[from]);
      const b = project(...AIRPORTS[to]);
      const dist = Math.hypot(b.x - a.x, b.y - a.y);
      flights.push({ from, to, start: now - stagger, duration: 3200 + dist * 6.5 });
    };

    const drawPlane = (p: Pt, angle: number) => {
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(angle);
      ctx.fillStyle = "#fff";
      ctx.shadowColor = accent;
      ctx.shadowBlur = 12;
      ctx.beginPath();
      // Small top-down airliner pointing along +x.
      ctx.moveTo(7, 0);
      ctx.lineTo(1, -1.4);
      ctx.lineTo(-1, -6);
      ctx.lineTo(-3, -6);
      ctx.lineTo(-2, -1.4);
      ctx.lineTo(-5.5, -1.2);
      ctx.lineTo(-7, -3.2);
      ctx.lineTo(-8, -3.2);
      ctx.lineTo(-7, 0);
      ctx.lineTo(-8, 3.2);
      ctx.lineTo(-7, 3.2);
      ctx.lineTo(-5.5, 1.2);
      ctx.lineTo(-2, 1.4);
      ctx.lineTo(-3, 6);
      ctx.lineTo(-1, 6);
      ctx.lineTo(1, 1.4);
      ctx.closePath();
      ctx.fill();
      ctx.restore();
    };

    const draw = (now: number) => {
      ctx.clearRect(0, 0, width, height);

      // Faint dot grid, like a radar screen
      ctx.fillStyle = "rgba(255,255,255,0.07)";
      const gap = 28;
      for (let y = gap / 2; y < height; y += gap) {
        for (let x = gap / 2; x < width; x += gap) ctx.fillRect(x - 0.75, y - 0.75, 1.5, 1.5);
      }

      // The whole network, faintly
      ctx.lineWidth = 1;
      ctx.strokeStyle = "rgba(255,255,255,0.07)";
      for (const [p, q] of ROUTES) {
        const a = project(...AIRPORTS[p]);
        const b = project(...AIRPORTS[q]);
        const c = control(a, b);
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.quadraticCurveTo(c.x, c.y, b.x, b.y);
        ctx.stroke();
      }

      // Flights
      for (let i = flights.length - 1; i >= 0; i--) {
        const f = flights[i];
        const t = (now - f.start) / f.duration;
        if (t >= 1) {
          arrivals[f.to] = now;
          flights.splice(i, 1);
          continue;
        }
        if (t < 0) continue;
        const a = project(...AIRPORTS[f.from]);
        const b = project(...AIRPORTS[f.to]);
        const c = control(a, b);
        const e = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; // ease in-out

        // Trail: short segments fading towards the tail
        const steps = 18;
        const t0 = Math.max(0, e - TRAIL);
        let prev = bezier(a, c, b, t0);
        for (let s = 1; s <= steps; s++) {
          const tt = t0 + ((e - t0) * s) / steps;
          const pt = bezier(a, c, b, tt);
          ctx.strokeStyle = accent;
          ctx.globalAlpha = (s / steps) * 0.9;
          ctx.lineWidth = 0.6 + (s / steps) * 1.6;
          ctx.beginPath();
          ctx.moveTo(prev.x, prev.y);
          ctx.lineTo(pt.x, pt.y);
          ctx.stroke();
          prev = pt;
        }
        ctx.globalAlpha = 1;

        const p = bezier(a, c, b, e);
        const ahead = bezier(a, c, b, Math.min(1, e + 0.01));
        drawPlane(p, Math.atan2(ahead.y - p.y, ahead.x - p.x));
      }

      // Airports, with a ring that expands when a plane lands
      ctx.font = `500 ${Math.max(9, Math.round(height / 85))}px "Martian Mono", monospace`;
      for (const [code, pos] of Object.entries(AIRPORTS)) {
        const p = project(...pos);
        const since = now - (arrivals[code] ?? -1e9);
        if (since < 1400) {
          const k = since / 1400;
          ctx.strokeStyle = accent;
          ctx.globalAlpha = 1 - k;
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.arc(p.x, p.y, 4 + k * 18, 0, Math.PI * 2);
          ctx.stroke();
          ctx.globalAlpha = 1;
        }
        ctx.fillStyle = accent;
        ctx.beginPath();
        ctx.arc(p.x, p.y, 3, 0, Math.PI * 2);
        ctx.fill();
        if (width >= 900) {
          ctx.fillStyle = "rgba(255,255,255,0.45)";
          ctx.fillText(code, p.x + 7, p.y - 6);
        }
      }

      // Fewer planes on a phone, where the network sits behind the text.
      const target = width < 900 ? 6 : MAX_FLIGHTS;
      while (flights.length < target) spawn(now, Math.random() * 1500);
    };

    const loop = (now: number) => {
      draw(now);
      raf = requestAnimationFrame(loop);
    };
    const start = () => {
      if (running || reduced || !visible || document.hidden) return;
      running = true;
      raf = requestAnimationFrame(loop);
    };
    const stop = () => {
      running = false;
      cancelAnimationFrame(raf);
    };

    resize();
    const t0 = performance.now();
    for (let i = 0; i < (width < 900 ? 6 : MAX_FLIGHTS); i++) spawn(t0, Math.random() * 4000);
    if (reduced) {
      // A still frame: planes caught mid-flight along their routes.
      draw(t0);
    }

    const ro = new ResizeObserver(() => {
      resize();
      if (!running) draw(performance.now());
    });
    ro.observe(canvas);

    const io = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      if (visible) start();
      else stop();
    });
    io.observe(canvas);

    const onVisibility = () => (document.hidden ? stop() : start());
    document.addEventListener("visibilitychange", onVisibility);

    start();
    return () => {
      stop();
      ro.disconnect();
      io.disconnect();
      themeObserver.disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  return <canvas ref={canvasRef} className={className} aria-hidden="true" />;
}
