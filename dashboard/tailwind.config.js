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
      dark: { bg: '#0b0e11', card: '#141920', border: '#262e39', hover: '#212832' },
      slate: {
        50:'#f5f7fa', 100:'#eef2f6', 200:'#dde3ea', 300:'#cfd6de', 400:'#a8b3bf',
        500:'#8794a3', 600:'#333d4b', 700:'#212832', 800:'#141920', 900:'#0b0e11', 950:'#07090c'
      },
      brand: { DEFAULT: '#00e701', gold: '#ffd700', dim: '#00a801' }
    }
  }},
  safelist: [
    { pattern: /^(bg|text|border)-(slate|blue|green|red|amber|purple|emerald)-(50|100|200|300|400|500|600|700|800|900)$/, variants: ['hover'] },
  ],
};
