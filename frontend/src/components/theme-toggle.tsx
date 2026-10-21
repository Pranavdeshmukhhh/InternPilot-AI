'use client';

import { useEffect, useState } from 'react';
import { Monitor, Moon, Sun } from 'lucide-react';

type Theme = 'system' | 'light' | 'dark';
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>('system');
  useEffect(() => {
    try { const stored = localStorage.getItem('internpilot-theme'); if (stored === 'light' || stored === 'dark') setTheme(stored); } catch { /* Theme preferences are optional when storage is unavailable. */ }
  }, []);
  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const apply = () => { const resolved = theme === 'system' ? media.matches ? 'dark' : 'light' : theme; document.documentElement.dataset.theme = resolved; document.documentElement.style.colorScheme = resolved; };
    apply(); media.addEventListener('change', apply);
    return () => media.removeEventListener('change', apply);
  }, [theme]);
  const Icon = theme === 'dark' ? Moon : theme === 'light' ? Sun : Monitor;
  return <label className="theme-toggle"><Icon size={16} /><select aria-label="Color theme" value={theme} onChange={event => { const value = event.target.value as Theme; setTheme(value); try { localStorage.setItem('internpilot-theme', value); } catch { /* Continue with the current appearance. */ } }}><option value="system">System</option><option value="light">Light</option><option value="dark">Dark</option></select></label>;
}
