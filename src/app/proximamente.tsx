import { useMemo, useState } from 'react';
import { Linking, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { Image } from 'expo-image';
import { SafeAreaView } from 'react-native-safe-area-context';
import { ThemedText } from '@/components/themed-text';
import { Colors, MaxContentWidth, Spacing } from '@/constants/theme';
import { todayIso } from '@/data';
import { useCinemaData } from '@/data/use-remote-data';

function formatDate(value?: string) {
  if (!value) return '';
  const d = new Date(`${value}T12:00:00`);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString('es-AR', { day:'2-digit', month:'long', year:'numeric' });
}

export default function ProximamenteScreen() {
  const today = todayIso();
  const { data, loading } = useCinemaData();
  const [failed, setFailed] = useState<Record<string, boolean>>({});
  const movies = useMemo(() => (data?.proximos_estrenos ?? [])
    .filter((m:any) => m.release_date && m.release_date >= today)
    .sort((a:any,b:any) => a.release_date.localeCompare(b.release_date)), [data, today]);

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.content}>
        <ThemedText type="small" themeColor="textSecondary">CINEMACENTER</ThemedText>
        <ThemedText type="title">Próximamente</ThemedText>
        <ThemedText themeColor="textSecondary" style={styles.subtitle}>Próximos estrenos de cine en Tucumán.</ThemedText>

        {loading && movies.length === 0 ? <View style={styles.empty}><ThemedText themeColor="textSecondary">Cargando próximos estrenos…</ThemedText></View> : null}
        {!loading && movies.length === 0 ? <View style={styles.empty}><ThemedText type="subtitle">No hay próximos estrenos publicados.</ThemedText></View> : null}

        {movies.map((movie:any) => {
          const poster = movie.poster || movie.metadata?.poster;
          const title = movie.title || movie.metadata?.title;
          const key = String(movie.id || title);
          return (
            <View key={key} style={styles.card}>
              {poster && !failed[key] ? (
                <Image source={{uri:poster}} style={styles.poster} contentFit="cover" onError={() => setFailed(x => ({...x,[key]:true}))} />
              ) : <View style={[styles.poster, styles.posterPlaceholder]}><ThemedText themeColor="textSecondary">Sin póster</ThemedText></View>}
              <View style={styles.cardBody}>
                <ThemedText type="subtitle" numberOfLines={3}>{title}</ThemedText>
                {movie.release_date ? <ThemedText style={styles.release}>Estreno: {formatDate(movie.release_date)}</ThemedText> : null}
                {movie.status ? <ThemedText themeColor="textSecondary">{movie.status}</ThemedText> : null}
                {movie.source_url ? <Pressable onPress={() => Linking.openURL(movie.source_url)} style={styles.button}><ThemedText style={styles.buttonText}>Ver información</ThemedText></Pressable> : null}
              </View>
            </View>
          );
        })}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles=StyleSheet.create({
  safe:{flex:1,backgroundColor:Colors.light.background},
  content:{width:'100%',maxWidth:MaxContentWidth,alignSelf:'center',paddingHorizontal:Spacing.three,paddingTop:12,paddingBottom:130},
  subtitle:{marginTop:5,marginBottom:20},
  empty:{padding:28,borderRadius:18,backgroundColor:Colors.light.backgroundElement,borderWidth:1,borderColor:Colors.light.border,alignItems:'center'},
  card:{backgroundColor:'#fff',borderRadius:18,borderWidth:1,borderColor:Colors.light.border,overflow:'hidden',marginBottom:12,flexDirection:'row'},
  poster:{width:105,height:155,backgroundColor:'#EEF1EF'},
  posterPlaceholder:{alignItems:'center',justifyContent:'center',padding:8},
  cardBody:{flex:1,padding:15,gap:7},
  release:{fontWeight:'800',color:Colors.light.primaryDark},
  button:{marginTop:'auto',alignSelf:'flex-start',backgroundColor:Colors.light.primary,borderRadius:12,paddingHorizontal:12,paddingVertical:9},
  buttonText:{color:'#fff',fontWeight:'800'},
});
