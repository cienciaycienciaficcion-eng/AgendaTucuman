import '@/global.css';
import { Platform } from 'react-native';

export const Colors = {
  light: {
    text: '#10201A',
    background: '#F5F7F4',
    backgroundElement: '#FFFFFF',
    backgroundSelected: '#DDEFE5',
    textSecondary: '#64736B',
    primary: '#17834B',
    primaryDark: '#0E6237',
    border: '#D7E1DB',
    accent: '#E6A21A',
    danger: '#C84C4C',
  },
  dark: {
    text: '#F4F8F5',
    background: '#0B120F',
    backgroundElement: '#131C17',
    backgroundSelected: '#193A29',
    textSecondary: '#A8B5AE',
    primary: '#45C77B',
    primaryDark: '#2EA461',
    border: '#26362D',
    accent: '#F0B83A',
    danger: '#E16B6B',
  },
} as const;

export type ThemeColor = keyof typeof Colors.light & keyof typeof Colors.dark;

export const Fonts = Platform.select({
  ios: {
    sans: 'system-ui',
    serif: 'ui-serif',
    rounded: 'ui-rounded',
    mono: 'ui-monospace',
  },
  default: {
    sans: 'normal',
    serif: 'serif',
    rounded: 'normal',
    mono: 'monospace',
  },
  web: {
    sans: 'var(--font-display)',
    serif: 'var(--font-serif)',
    rounded: 'var(--font-rounded)',
    mono: 'var(--font-mono)',
  },
});

export const Spacing = {
  half: 2,
  one: 4,
  two: 8,
  three: 16,
  four: 24,
  five: 32,
  six: 64,
} as const;

export const BottomTabInset = Platform.select({ ios: 50, android: 80 }) ?? 0;
export const MaxContentWidth = 900;
