"use client";

import { useState, useEffect, useRef } from "react";

interface CounterProps {
  to: number;
  suf?: string;
  duration?: number;
  decimals?: number;
}

export default function Counter({ to, suf = "", duration = 1500, decimals = 1 }: CounterProps) {
  const [val, setVal] = useState(0);
  const ref = useRef<HTMLDivElement>(null);
  const animated = useRef(false);

  useEffect(() => {
    const obs = new IntersectionObserver(([e]) => {
      if (e.isIntersecting && !animated.current) {
        animated.current = true;
        let startTimestamp: number | null = null;
        
        const step = (timestamp: number) => {
          if (!startTimestamp) startTimestamp = timestamp;
          const progress = Math.min((timestamp - startTimestamp) / duration, 1);
          
          // Easing function: easeOutExpo
          const easedProgress = progress === 1 ? 1 : 1 - Math.pow(2, -10 * progress);
          
          const currentVal = easedProgress * to;
          setVal(currentVal);
          
          if (progress < 1) {
            window.requestAnimationFrame(step);
          }
        };
        
        window.requestAnimationFrame(step);
      }
    }, { threshold: 0.1 });

    if (ref.current) obs.observe(ref.current);
    return () => obs.disconnect();
  }, [to, duration]);

  const displayVal = decimals > 0 
    ? val.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
    : Math.round(val).toLocaleString();

  return (
    <div ref={ref} style={{ display: "inline-block" }}>
      {displayVal}
      {suf && <span className="unit" style={{ fontSize: "0.6em", marginLeft: "2px", verticalAlign: "middle" }}>{suf}</span>}
    </div>
  );
}
