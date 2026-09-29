import { useMemo } from 'react';
import { Linking, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { ThemedText } from '@/components/themed-text';
import { Colors, MaxContentWidth, Spacing } from '@/constants/theme';
import { todayIso } from '@/data';
import { useCinemaData } from '@/data/use-remote-data';

export default function CineScreen() {
  const today = todayIso();
  const { data: cinemaData } = useCinemaData();

  const movies = useMemo(() => {
    return cinemaData.cartelera.movies
      .filter(movie => movie.occurrences.some(o => o.date >= today))
      .reduce((acc: any[], movie) => {
        const existing = acc.find(x => x.title === movie.title);
        if (existing) {
          existing.variants.push(movie);
        } else {
          acc.push({ title: movie.title, variants: [movie] });
        }
        return acc;
      }, []);
  }, [today]);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <View style={{flex:1}}>
            <ThemedText type="title">Cine</ThemedText>
            <ThemedText themeColor="textSecondary">
              Cinemacenter Tucumán · {cinemaData.cartelera.week_start} al {cinemaData.cartelera.week_end}
            </ThemedText>
          </View>
          <Pressable onPress={() => Linking.openURL('https://www.cinemacenter.com.ar/cartelera#contenido')} style={styles.source}>
            <ThemedText style={styles.sourceText}>Sitio oficial</ThemedText>
          </Pressable>
        </View>

        {movies.map((movie: any) => (
          <View key={movie.title} style={styles.card}>
            <ThemedText type="subtitle">{movie.title}</ThemedText>
            {movie.variants.map((variant: any) => (
              <View key={variant.id} style={styles.variant}>
                <View style={styles.badges}>
                  <View style={styles.badge}><ThemedText style={styles.badgeText}>{variant.format}</ThemedText></View>
                  <View style={[styles.badge, styles.badgeSecondary]}><ThemedText style={styles.badgeText}>{variant.language}</ThemedText></View>
                </View>
                <View style={styles.times}>
                  {variant.occurrences.filter((o: any) => o.date >= today).slice(0, 12).map((o: any) => (
                    <View key={o.datetime} style={styles.time}>
                      <ThemedText style={styles.timeDate}>{o.date.slice(8,10)}/{o.date.slice(5,7)}</ThemedText>
                      <ThemedText style={styles.timeText}>{o.time}</ThemedText>
                    </View>
                  ))}
                </View>
              </View>
            ))}
          </View>
        ))}

        <View style={styles.note}>
          <ThemedText style={styles.noteTitle}>Cartelera oficial</ThemedText>
          <ThemedText themeColor="textSecondary">
            Los horarios se obtienen del PDF oficial de Cinemacenter Tucumán (cityId=13).
          </ThemedText>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe:{flex:1,backgroundColor:Colors.light.background},
  content:{width:'100%',maxWidth:MaxContentWidth,alignSelf:'center',padding:Spacing.three,paddingBottom:110},
  header:{flexDirection:'row',alignItems:'center',gap:12,marginBottom:18},
  source:{backgroundColor:Colors.light.primary,borderRadius:14,paddingHorizontal:12,paddingVertical:9},
  sourceText:{color:'#fff',fontWeight:'700',fontSize:12},
  card:{backgroundColor:'#fff',borderWidth:1,borderColor:Colors.light.border,borderRadius:18,padding:16,marginBottom:12},
  variant:{marginTop:12,paddingTop:12,borderTopWidth:1,borderTopColor:'#E9EFEB'},
  badges:{flexDirection:'row',gap:6,marginBottom:10},
  badge:{backgroundColor:Colors.light.primary,borderRadius:7,paddingHorizontal:8,paddingVertical:4},
  badgeSecondary:{backgroundColor:Colors.light.primaryDark},
  badgeText:{color:'#fff',fontSize:11,fontWeight:'800'},
  times:{flexDirection:'row',flexWrap:'wrap',gap:7},
  time:{borderWidth:1,borderColor:Colors.light.border,borderRadius:10,paddingHorizontal:9,paddingVertical:7,alignItems:'center',minWidth:67},
  timeDate:{fontSize:10,color:Colors.light.textSecondary},
  timeText:{fontSize:15,fontWeight:'800'},
  note:{backgroundColor:'#EAF5EE',borderRadius:16,padding:16,marginTop:4},
  noteTitle:{fontWeight:'800',marginBottom:4,color:Colors.light.primaryDark},
});
