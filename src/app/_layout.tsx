import { DefaultTheme, ThemeProvider } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { AnimatedSplashOverlay } from '@/components/animated-icon';
import AppTabs from '@/components/app-tabs';
import { RadioProvider } from '@/context/radio-context';
import AppHeader from '@/components/app-header';
import { View } from 'react-native';

SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  return (
    <ThemeProvider value={DefaultTheme}>
      <StatusBar style="dark" backgroundColor="#F8F8F7" />
      <RadioProvider>
        <View style={{ flex: 1, backgroundColor: '#F8F8F7' }}>
          <AppHeader />
          <View style={{ flex: 1 }}>
            <AnimatedSplashOverlay />
            <AppTabs />
          </View>
        </View>
      </RadioProvider>
    </ThemeProvider>
  );
}
