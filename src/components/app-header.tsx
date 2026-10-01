import { useEffect, useMemo, useState } from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';
import { useRouter, useSegments } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Colors } from '@/constants/theme';

const WEATHER_URL = 'https://api.open-meteo.com/v1/forecast?latitude=-26.8083&longitude=-65.2176&current=temperature_2m,apparent_temperature,weather_code,is_day&daily=temperature_2m_max,temperature_2m_min,weather_code&timezone=America%2FArgentina%2FTucuman&forecast_days=1';

const titles: Record<string, string> = {
  index: 'AGENDA',
  calendar: 'CALENDARIO',
  cine: 'CINE',
  radio: 'RADIO',
  services: 'SERVICIOS',
  more: 'MÁS',
  weather: 'CLIMA',
};

function weatherIcon(code?: number, isDay = true) {
  if (code == null) return '☁️';
  if (code === 0) return isDay ? '☀️' : '🌙';
  if (code <= 3) return isDay ? '🌤️' : '☁️';
  if (code <= 48) return '🌫️';
  if (code <= 67 || (code >= 80 && code <= 82)) return '🌧️';
  if (code >= 95) return '⛈️';
  return '☁️';
}

export default function AppHeader() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const segments = useSegments();
  const [weather, setWeather] = useState<any | null>(null);

  const title = useMemo(() => {
    const segment = String(segments[segments.length - 1] || 'index');
    return titles[segment] || 'AGENDA';
  }, [segments]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const response = await fetch(WEATHER_URL);
        if (!response.ok) throw new Error('weather request failed');
        const data = await response.json();
        if (!cancelled) setWeather(data);
      } catch {
        if (!cancelled) setWeather(null);
      }
    };
    load();
    const timer = setInterval(load, 15 * 60 * 1000);
    return () => { cancelled = true; clearInterval(timer); };
  }, []);

  const current = weather?.current;
  const daily = weather?.daily;
  const temp = typeof current?.temperature_2m === 'number' ? Math.round(current.temperature_2m) : null;
  const max = typeof daily?.temperature_2m_max?.[0] === 'number' ? Math.round(daily.temperature_2m_max[0]) : null;
  const min = typeof daily?.temperature_2m_min?.[0] === 'number' ? Math.round(daily.temperature_2m_min[0]) : null;

  return (
    <View style={[styles.wrapper, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <View style={styles.brand}>
          <Image source={require('../../assets/images/agenda-logo.png')} style={styles.logo} resizeMode="contain" />
          <View style={styles.brandText}>
            <Text style={styles.appName}>AGENDA TUCUMÁN</Text>
            <Text style={styles.section}>{title}</Text>
          </View>
        </View>

        <Pressable onPress={() => router.push('/weather')} style={({ pressed }) => [styles.weather, pressed && styles.pressed]}>
          <Text style={styles.weatherIcon}>{weatherIcon(current?.weather_code, current?.is_day === 1)}</Text>
          <View>
            <Text style={styles.temperature}>{temp != null ? `${temp}°` : '--°'}</Text>
            <Text style={styles.range}>{min != null && max != null ? `${min}° / ${max}°` : 'Clima'}</Text>
          </View>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: { backgroundColor: Colors.light.backgroundElement, borderBottomWidth: 1, borderBottomColor: Colors.light.border, zIndex: 20 },
  header: { minHeight: 68, paddingHorizontal: 16, paddingVertical: 9, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  brand: { flexDirection: 'row', alignItems: 'center', flex: 1, minWidth: 0 },
  logo: { width: 40, height: 40, marginRight: 10 },
  brandText: { minWidth: 0 },
  appName: { color: Colors.light.primaryDark, fontSize: 12, fontWeight: '800', letterSpacing: 0.7 },
  section: { color: Colors.light.text, fontSize: 20, fontWeight: '900', marginTop: 1 },
  weather: { flexDirection: 'row', alignItems: 'center', gap: 7, paddingLeft: 10, paddingVertical: 4 },
  weatherIcon: { fontSize: 25 },
  temperature: { color: Colors.light.text, fontSize: 18, fontWeight: '900', textAlign: 'right' },
  range: { color: Colors.light.textSecondary, fontSize: 10, fontWeight: '700', textAlign: 'right' },
  pressed: { opacity: 0.65 },
});
