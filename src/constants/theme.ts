import '@/global.css';
import { Platform } from 'react-native';

export const Colors = {
  light: {
    text: '#242627',
    background: '#F8F8F7',
    backgroundElement: '#FFFFFF',
    backgroundSelected: '#FFF0E6',
    textSecondary: '#4B4F51',
    primary: '#F27616',
    primaryDark: '#A94600',
    border: '#E8DDD5',
    accent: '#F27616',
    danger: '#C84C4C',
  },
  dark: {
    text: '#F7F7F5',
    background: '#171819',
    backgroundElement: '#222324',
    backgroundSelected: '#3A261A',
    textSecondary: '#B9B9B7',
    primary: '#FF8A2A',
    primaryDark: '#F27616',
    border: '#3B3734',
    accent: '#FF8A2A',
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
