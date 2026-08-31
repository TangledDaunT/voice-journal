/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['class'],
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    container: {
      center: true,
      padding: '2rem',
      screens: {
        '2xl': '1400px',
      },
    },
    extend: {
      colors: {
        // Earth tones palette
        border: '#D4C4B5',
        input: '#F5F0EB',
        ring: '#8B7355',
        background: '#FDF8F3',
        foreground: '#3D2914',

        primary: {
          DEFAULT: '#8B7355',
          foreground: '#FDF8F3',
          50: '#FDF8F3',
          100: '#F5F0EB',
          200: '#E8DDD4',
          300: '#D4C4B5',
          400: '#B8A085',
          500: '#8B7355',
          600: '#6B5A45',
          700: '#554835',
          800: '#3D2914',
          900: '#2A1D0E',
        },

        secondary: {
          DEFAULT: '#CD853F',
          foreground: '#FDF8F3',
          50: '#FDF5EDE',
          100: '#FAEBD7',
          200: '#F5D5A8',
          300: '#EDB86E',
          400: '#E09837',
          500: '#CD853F',
          600: '#A66628',
          700: '#7F4B1C',
          800: '#583414',
          900: '#3D2410',
        },

        accent: {
          DEFAULT: '#556B2F',
          foreground: '#FDF8F3',
          50: '#F4F6EE',
          100: '#E9ECDC',
          200: '#D3D9BA',
          300: '#B4C08D',
          400: '#94A261',
          500: '#556B2F',
          600: '#435625',
          700: '#34421C',
          800: '#262E15',
          900: '#1A1E0D',
        },

        muted: {
          DEFAULT: '#9E8B7A',
          foreground: '#6B5A45',
        },

        destructive: {
          DEFAULT: '#C4413D',
          foreground: '#FDF8F3',
        },

        success: {
          DEFAULT: '#556B2F',
          foreground: '#FDF8F3',
        },

        warning: {
          DEFAULT: '#CD853F',
          foreground: '#3D2914',
        },

        card: {
          DEFAULT: '#FFFFFF',
          foreground: '#3D2914',
        },

        popover: {
          DEFAULT: '#FFFFFF',
          foreground: '#3D2914',
        },
      },
      borderRadius: {
        lg: '0.75rem',
        md: '0.5rem',
        sm: '0.25rem',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        display: ['Merriweather', 'Georgia', 'serif'],
      },
      keyframes: {
        'accordion-down': {
          from: { height: '0' },
          to: { height: 'var(--radix-accordion-content-height)' },
        },
        'accordion-up': {
          from: { height: 'var(--radix-accordion-content-height)' },
          to: { height: '0' },
        },
        'slide-in-right': {
          from: { transform: 'translateX(100%)' },
          to: { transform: 'translateX(0)' },
        },
        'slide-out-right': {
          from: { transform: 'translateX(0)' },
          to: { transform: 'translateX(100%)' },
        },
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out',
        'slide-in-right': 'slide-in-right 0.3s ease-out',
        'slide-out-right': 'slide-out-right 0.3s ease-out',
      },
    },
  },
  plugins: [],
}
