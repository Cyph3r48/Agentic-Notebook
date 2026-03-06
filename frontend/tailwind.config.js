/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Dark blue base - using CSS variables for theme switching
        'dark-base': 'var(--color-dark-base)',
        'dark-surface': 'var(--color-dark-surface)',
        'dark-elevated': 'var(--color-dark-elevated)',
        
        // Blue tones
        'blue': {
          50: '#e6f0ff',
          100: '#cce0ff',
          200: '#99c2ff',
          300: '#66a3ff',
          400: '#3385ff',
          500: '#0066ff', // Primary blue
          600: '#0052cc',
          700: '#003d99',
          800: '#002966',
          900: '#001433',
          950: '#000a1a',
        },
        
        // Purple accents
        'purple': {
          50: '#f5f0ff',
          100: '#ebe0ff',
          200: '#d6c2ff',
          300: '#c2a3ff',
          400: '#ad85ff',
          500: '#9966ff', // Primary purple
          600: '#7a52cc',
          700: '#5c3d99',
          800: '#3d2966',
          900: '#1f1433',
        },
        
        // Claude orange accent
        'claude-orange': {
          50: '#fff5eb',
          100: '#ffebd6',
          200: '#ffd6ad',
          300: '#ffc285',
          400: '#ffad5c',
          500: '#ff9933', // Claude orange
          600: '#cc7a29',
          700: '#995c1f',
          800: '#663d14',
          900: '#331f0a',
        },
        
        // Light blues
        'light-blue': {
          50: '#e6f7ff',
          100: '#ccefff',
          200: '#99dfff',
          300: '#66cfff',
          400: '#33bfff',
          500: '#00afff',
          600: '#008fcc',
          700: '#006b99',
          800: '#004766',
          900: '#002433',
        },
        
        // Glass effect
        'glass': {
          'white': 'rgba(255, 255, 255, 0.05)',
          'border': 'rgba(255, 255, 255, 0.1)',
          'hover': 'rgba(255, 255, 255, 0.08)',
        }
      },
      
      backdropBlur: {
        xs: '2px',
      },
      
      animation: {
        'fade-in': 'fadeIn 0.5s ease-in-out',
        'slide-up': 'slideUp 0.5s ease-out',
        'slide-down': 'slideDown 0.5s ease-out',
        'scale-in': 'scaleIn 0.3s ease-out',
        'glow': 'glow 2s ease-in-out infinite',
        'float': 'float 3s ease-in-out infinite',
      },
      
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { transform: 'translateY(20px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        slideDown: {
          '0%': { transform: 'translateY(-20px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        scaleIn: {
          '0%': { transform: 'scale(0.95)', opacity: '0' },
          '100%': { transform: 'scale(1)', opacity: '1' },
        },
        glow: {
          '0%, 100%': { boxShadow: '0 0 20px rgba(0, 102, 255, 0.3)' },
          '50%': { boxShadow: '0 0 30px rgba(0, 102, 255, 0.6)' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-10px)' },
        },
      },
      
      boxShadow: {
        'glass': '0 8px 32px 0 rgba(0, 102, 255, 0.1)',
        'glass-lg': '0 12px 48px 0 rgba(0, 102, 255, 0.15)',
        'glass-xl': '0 20px 60px 0 rgba(0, 102, 255, 0.2)',
        'glow-blue': '0 0 20px rgba(0, 102, 255, 0.4)',
        'glow-purple': '0 0 20px rgba(153, 102, 255, 0.4)',
        'glow-orange': '0 0 20px rgba(255, 153, 51, 0.4)',
      },
      
      fontFamily: {
        'display': ['Space Grotesk', 'system-ui', 'sans-serif'],
        'body': ['Inter', 'system-ui', 'sans-serif'],
        'mono': ['JetBrains Mono', 'monospace'],
      },
    },
  },
  plugins: [],
}
