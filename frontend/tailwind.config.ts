import type { Config } from 'tailwindcss'

/** Wrap a CSS-variable color so Tailwind opacity modifiers work via color-mix(). */
function v(variable: string) {
  return ({ opacityValue }: { opacityValue?: string }) => {
    if (opacityValue !== undefined) {
      const pct = Math.round(Number.parseFloat(opacityValue) * 100)
      return `color-mix(in oklch, var(${variable}) ${pct}%, transparent)`
    }
    return `var(${variable})`
  }
}

export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg:             v('--bg'),
        surface:        v('--surface'),
        'surface-2':    v('--surface-2'),
        border:         v('--border'),
        text:           v('--text'),
        muted:          v('--text-muted'),
        accent:         v('--accent'),
        'accent-strong': v('--accent-strong'),
        'sev-critical': v('--sev-critical'),
        'sev-high':     v('--sev-high'),
        'sev-medium':   v('--sev-medium'),
        'sev-low':      v('--sev-low'),
        'sev-ok':       v('--sev-ok'),
        'conn-ok':      v('--conn-ok'),
        'conn-err':     v('--conn-err'),
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
} satisfies Config
