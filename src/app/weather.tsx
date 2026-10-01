import { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { ThemedText } from '@/components/themed-text';
import { Colors, MaxContentWidth, Spacing } from '@/constants/theme';

const WEATHER_URL = 'https://api.open-meteo.com/v1/forecast?latitude=-26.8083&longitude=-65.2176&current=temperature_2m,apparent_temperature,weather_code,wind_speed_10m,relative_humidity_2m,is_day&daily=temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max&timezone=America%2FArgentina%2FTucuman&forecast_days=5';

function description(code?: number) {
  if (code === 0) return 'Despejado';
  if (code === 1) return 'Mayormente despejado';
  if (code === 2) return 'Parcialmente nublado';
  if (code === 3) return 'Nublado';
  if (code === 45 || code === 48) return 'Niebla';
  if (code != null && code >= 51 && code <= 57) return 'Llovizna';
  if (code != null && code >= 61 && code <= 67) return 'Lluvia';
  if (code != null && code >= 71 && code <= 77) return 'Nieve';
  if (code != null && code >= 80 && code <= 82) return 'Chaparrones';
  if (code != null && code >= 95) return 'Tormenta';
  return 'Condiciones variables';
}
function icon(code?: number) {
  if (code === 0) return '☀️';
  if (code != null && code <= 3) return '🌤️';
  if (code === 45 || code === 48) return '🌫️';
  if (code != null && code >= 95) return '⛈️';
  if (code != null && code >= 51) return '🌧️';
  return '☁️';
}

export default function WeatherScreen() {
  const router = useRouter();
  const [data, setData] = useState<any | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch(WEATHER_URL)
      .then(r => { if (!r.ok) throw new Error(); return r.json(); })
      .then(json => { if (!cancelled) setData(json); })
      .catch(() => { if (!cancelled) setError(true); });
    return () => { cancelled = true; };
  }, []);

  const current = data?.current;
  const daily = data?.daily;
  const dates: string[] = daily?.time ?? [];

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.topRow}>
          <ThemedText type="title">Clima</ThemedText>
          <ThemedText themeColor="textSecondary" onPress={() => router.back()}>Volver</ThemedText>
        </View>
        <ThemedText themeColor="textSecondary" style={styles.place}>San Miguel de Tucumán</ThemedText>

        {!data && !error ? <ActivityIndicator size="large" color={Colors.light.primary} style={styles.loader} /> : null}
        {error ? <View style={styles.card}><ThemedText type="subtitle">No se pudo cargar el clima</ThemedText><ThemedText themeColor="textSecondary">Intentá nuevamente en unos minutos.</ThemedText></View> : null}

        {current ? (
          <View style={styles.currentCard}>
            <ThemedText style={styles.bigIcon}>{icon(current.weather_code)}</ThemedText>
            <View style={{ flex: 1 }}>
              <ThemedText style={styles.bigTemp}>{Math.round(current.temperature_2m)}°</ThemedText>
              <ThemedText type="subtitle">{description(current.weather_code)}</ThemedText>
              <ThemedText themeColor="textSecondary">Sensación {Math.round(current.apparent_temperature)}° · Humedad {current.relative_humidity_2m}%</ThemedText>
              <ThemedText themeColor="textSecondary">Viento {Math.round(current.wind_speed_10m)} km/h</ThemedText>
            </View>
          </View>
        ) : null}

        {dates.map((date, index) => (
          <View key={date} style={styles.dayCard}>
            <View style={styles.dayIcon}><ThemedText style={{fontSize:24}}>{icon(daily.weather_code?.[index])}</ThemedText></View>
            <View style={{flex:1}}>
              <ThemedText type="subtitle">{index === 0 ? 'Hoy' : new Date(`${date}T12:00:00`).toLocaleDateString('es-AR', { weekday:'long', day:'2-digit', month:'2-digit' })}</ThemedText>
              <ThemedText themeColor="textSecondary">{description(daily.weather_code?.[index])} · Lluvia {daily.precipitation_probability_max?.[index] ?? 0}%</ThemedText>
            </View>
            <ThemedText style={styles.dayTemp}>{Math.round(daily.temperature_2m_min?.[index] ?? 0)}° / {Math.round(daily.temperature_2m_max?.[index] ?? 0)}°</ThemedText>
          </View>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe:{flex:1,backgroundColor:Colors.light.background},
  content:{width:'100%',maxWidth:MaxContentWidth,alignSelf:'center',paddingHorizontal:Spacing.three,paddingTop:18,paddingBottom:40},
  topRow:{flexDirection:'row',justifyContent:'space-between',alignItems:'center'},
  place:{marginTop:3,marginBottom:18},
  loader:{marginVertical:50},
  currentCard:{backgroundColor:Colors.light.backgroundElement,borderWidth:1,borderColor:Colors.light.border,borderRadius:22,padding:20,flexDirection:'row',alignItems:'center',gap:18},
  bigIcon:{fontSize:52},
  bigTemp:{fontSize:44,fontWeight:'900',lineHeight:48},
  card:{backgroundColor:Colors.light.backgroundElement,borderRadius:18,padding:20,borderWidth:1,borderColor:Colors.light.border},
  dayCard:{marginTop:10,backgroundColor:Colors.light.backgroundElement,borderWidth:1,borderColor:Colors.light.border,borderRadius:18,padding:14,flexDirection:'row',alignItems:'center',gap:12},
  dayIcon:{width:44,alignItems:'center'},
  dayTemp:{fontSize:14,fontWeight:'800'},
});
