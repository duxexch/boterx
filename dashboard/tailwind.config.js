// Tailwind build config for the pre-built stylesheet dashboard/static/css/tailwind.build.css
// Rebuild after adding new Tailwind classes to templates/JS:  ./build_css.sh
module.exports = {
  darkMode: 'class',
  content: [
    './dashboard/templates/**/*.html',
    './dashboard/static/js/**/*.js',
  ],
  theme: { extend: {
    fontFamily: { cairo: ['Cairo', 'Segoe UI', 'Tahoma', 'sans-serif'] },
    colors: {
      dark: { bg: '#0F172A', card: '#1E293B', border: '#334155', hover: '#334155' },
      brand: { DEFAULT: '#00ff88', gold: '#00ff88', dim: '#00b35f' }
    }
  }},
  safelist: [
    { pattern: /^(bg|text|border)-(slate|blue|green|red|amber|purple|emerald)-(50|100|200|300|400|500|600|700|800|900)$/, variants: ['hover'] },
  ],
};
