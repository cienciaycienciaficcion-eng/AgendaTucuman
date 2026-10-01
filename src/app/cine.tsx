import { useMemo, useState } from 'react';
import { Linking, Modal, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { Image } from 'expo-image';
import { SafeAreaView } from 'react-native-safe-area-context';
import { ThemedText } from '@/components/themed-text';
import { Colors, MaxContentWidth, Spacing } from '@/constants/theme';
import { todayIso } from '@/data';
import { useCinemaData } from '@/data/use-remote-data';

function formatReleaseDate(value?: string) {
  if (!value) return '';
  const date = new Date(`${value}T12:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString('es-AR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}

function MovieDetails({ movie, visible, onClose }: { movie: any | null; visible: boolean; onClose: () => void }) {
  if (!movie) return null;
  const metadata = movie.metadata ?? {};
  const genres = Array.isArray(metadata.genres) ? metadata.genres : [];
  const director = Array.isArray(metadata.director) ? metadata.director : [];
  const cast = Array.isArray(metadata.cast) ? metadata.cast : [];

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View style={styles.modalBackdrop}>
        <View style={styles.modalCard}>
          <ScrollView contentContainerStyle={styles.modalContent}>
            <View style={styles.modalHeader}>
              <ThemedText type="subtitle" numberOfLines={2} style={styles.modalHeaderTitle}>
                {metadata.title || movie.title}
              </ThemedText>
              <Pressable onPress={onClose} style={styles.closeButton}>
                <ThemedText style={styles.closeText}>Cerrar</ThemedText>
              </Pressable>
            </View>

            {metadata.poster ? (
              <Image source={{ uri: metadata.poster }} style={styles.poster} contentFit="cover" />
            ) : (
              <View style={styles.posterPlaceholder}>
                <ThemedText themeColor="textSecondary">Imagen no disponible</ThemedText>
              </View>
            )}

            <ThemedText type="title" style={styles.modalTitle}>
              {metadata.title || movie.title}
            </ThemedText>

            {metadata.original_title ? (
              <ThemedText themeColor="textSecondary" style={styles.originalTitle}>
                Título original: {metadata.original_title}
              </ThemedText>
            ) : null}

            <View style={styles.metadataGrid}>
              {metadata.year ? <Info label="Año" value={String(metadata.year)} /> : null}
              {metadata.release_date ? <Info label="Estreno" value={formatReleaseDate(metadata.release_date)} /> : null}
              {metadata.duration_minutes ? <Info label="Duración" value={`${metadata.duration_minutes} min`} /> : null}
            </View>

            {genres.length ? <InfoLine label="Géneros" value={genres.join(' · ')} /> : null}
            {director.length ? <InfoLine label="Director" value={director.join(', ')} /> : null}
            {cast.length ? <InfoLine label="Actores" value={cast.join(', ')} /> : null}
            {metadata.nationality ? <InfoLine label="Nacionalidad" value={String(metadata.nationality)} /> : null}
            {metadata.rating ? <InfoLine label="Clasificación" value={String(metadata.rating)} /> : null}
            {metadata.distributor ? <InfoLine label="Distribuidora" value={String(metadata.distributor)} /> : null}

            {metadata.synopsis ? (
              <View style={styles.section}>
                <ThemedText type="subtitle" style={styles.sectionTitle}>Sinopsis</ThemedText>
                <ThemedText style={styles.synopsis}>{metadata.synopsis}</ThemedText>
              </View>
            ) : null}

            <View style={styles.section}>
              <ThemedText type="subtitle" style={styles.sectionTitle}>Funciones</ThemedText>
              {movie.variants.map((variant: any) => (
                <View key={variant.id} style={styles.modalVariant}>
                  <View style={styles.badges}>
                    <View style={styles.badge}><ThemedText style={styles.badgeText}>{variant.format}</ThemedText></View>
                    <View style={[styles.badge, styles.badgeSecondary]}><ThemedText style={styles.badgeText}>{variant.language}</ThemedText></View>
                  </View>
                  <ThemedText themeColor="textSecondary">
                    {variant.occurrences
                      .filter((o: any) => o.date >= todayIso())
                      .map((o: any) => `${o.date.slice(8, 10)}/${o.date.slice(5, 7)} ${o.time}`)
                      .join(' · ')}
                  </ThemedText>
                </View>
              ))}
            </View>

            {metadata.source_url ? (
              <Pressable style={styles.infoLink} onPress={() => Linking.openURL(metadata.source_url)}>
                <ThemedText style={styles.infoLinkText}>Ver ficha en Cinemacenter</ThemedText>
              </Pressable>
            ) : null}
            {metadata.imdb_url ? (
              <Pressable style={[styles.infoLink, { marginTop: 8 }]} onPress={() => Linking.openURL(metadata.imdb_url)}>
                <ThemedText style={styles.infoLinkText}>Ver ficha en IMDb</ThemedText>
              </Pressable>
            ) : null}
            {metadata.trailer ? (
              <Pressable style={[styles.infoLink, { marginTop: 8 }]} onPress={() => Linking.openURL(metadata.trailer)}>
                <ThemedText style={styles.infoLinkText}>Ver tráiler</ThemedText>
              </Pressable>
            ) : null}
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.infoBox}>
      <ThemedText type="smallBold" themeColor="textSecondary">{label}</ThemedText>
      <ThemedText style={styles.infoValue}>{value}</ThemedText>
    </View>
  );
}

function InfoLine({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.infoLine}>
      <ThemedText type="smallBold" themeColor="textSecondary">{label}</ThemedText>
      <ThemedText style={styles.infoLineValue}>{value}</ThemedText>
    </View>
  );
}

export default function CineScreen() {
  const today = todayIso();
  const { data: cinemaData, loading } = useCinemaData();
  const [selectedMovie, setSelectedMovie] = useState<any | null>(null);

  const movies = useMemo(() => {
    return (cinemaData?.cartelera?.movies ?? [])
      .filter((movie: any) => movie.occurrences?.some((o: any) => o.date >= today))
      .reduce((acc: any[], movie: any) => {
        const existing = acc.find(x => x.title === movie.title);
        if (existing) existing.variants.push(movie);
        else acc.push({ title: movie.title, variants: [movie], metadata: movie.metadata });
        return acc;
      }, []);
  }, [cinemaData, today]);

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <View style={{ flex: 1 }}>
            <ThemedText type="title">Cine</ThemedText>
            <ThemedText themeColor="textSecondary">
              Cinemacenter Tucumán · {cinemaData?.cartelera?.week_start} al {cinemaData?.cartelera?.week_end}
            </ThemedText>
          </View>
          <Pressable onPress={() => Linking.openURL('https://www.cinemacenter.com.ar/cartelera#contenido')} style={styles.source}>
            <ThemedText style={styles.sourceText}>Sitio oficial</ThemedText>
          </Pressable>
        </View>

        {loading && movies.length === 0 ? (
          <View style={styles.loadingBox}>
            <ThemedText themeColor="textSecondary">Cargando cartelera…</ThemedText>
          </View>
        ) : null}

        {movies.map((movie: any) => (
          <Pressable
            key={movie.title}
            style={({ pressed }) => [styles.card, pressed && { opacity: 0.78 }]}
            onPress={() => setSelectedMovie(movie)}
          >
            <View style={styles.movieHeader}>
              {movie.metadata?.poster ? (
                <Image source={{ uri: movie.metadata.poster }} style={styles.thumb} contentFit="cover" />
              ) : null}
              <View style={{ flex: 1 }}>
                <ThemedText type="subtitle" style={styles.movieTitle}>{movie.metadata?.title || movie.title}</ThemedText>
                {movie.metadata?.original_title ? (
                  <ThemedText themeColor="textSecondary" style={styles.originalSmall}>{movie.metadata.original_title}</ThemedText>
                ) : null}
                <ThemedText themeColor="textSecondary" style={styles.movieInfo}>
                  Toca para ver la ficha completa
                </ThemedText>
              </View>
            </View>

            {movie.variants.map((variant: any) => (
              <View key={variant.id} style={styles.variant}>
                <View style={styles.badges}>
                  <View style={styles.badge}><ThemedText style={styles.badgeText}>{variant.format}</ThemedText></View>
                  <View style={[styles.badge, styles.badgeSecondary]}><ThemedText style={styles.badgeText}>{variant.language}</ThemedText></View>
                </View>
                <View style={styles.times}>
                  {variant.occurrences.filter((o: any) => o.date >= today).slice(0, 12).map((o: any) => (
                    <View key={o.datetime} style={styles.time}>
                      <ThemedText style={styles.timeDate}>{o.date.slice(8, 10)}/{o.date.slice(5, 7)}</ThemedText>
                      <ThemedText style={styles.timeText}>{o.time}</ThemedText>
                    </View>
                  ))}
                </View>
              </View>
            ))}
          </Pressable>
        ))}
      </ScrollView>

      <MovieDetails movie={selectedMovie} visible={Boolean(selectedMovie)} onClose={() => setSelectedMovie(null)} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe:{flex:1,backgroundColor:Colors.light.background},
  content:{width:'100%',maxWidth:MaxContentWidth,alignSelf:'center',paddingHorizontal:Spacing.three,paddingTop:12,paddingBottom:130},
  header:{flexDirection:'row',alignItems:'center',gap:12,marginBottom:18},
  source:{backgroundColor:Colors.light.primary,borderRadius:14,paddingHorizontal:12,paddingVertical:9},
  sourceText:{color:'#fff',fontWeight:'700',fontSize:12},
  card:{backgroundColor:'#fff',borderWidth:1,borderColor:Colors.light.border,borderRadius:18,padding:16,marginBottom:12},
  movieHeader:{flexDirection:'row',gap:12,alignItems:'center'},
  thumb:{width:62,height:88,borderRadius:10,backgroundColor:'#E8E8E8'},
  movieTitle:{color:Colors.light.text,fontSize:24,lineHeight:29},
  originalSmall:{fontSize:12,marginTop:2},
  movieInfo:{marginTop:4,fontSize:13},
  variant:{marginTop:12,paddingTop:12,borderTopWidth:1,borderTopColor:'#E9EFEB'},
  badges:{flexDirection:'row',gap:6,marginBottom:10},
  badge:{backgroundColor:Colors.light.primary,borderRadius:7,paddingHorizontal:8,paddingVertical:4},
  badgeSecondary:{backgroundColor:Colors.light.primaryDark},
  badgeText:{color:'#fff',fontSize:11,fontWeight:'800'},
  times:{flexDirection:'row',flexWrap:'wrap',gap:7},
  time:{borderWidth:1,borderColor:Colors.light.border,borderRadius:10,paddingHorizontal:9,paddingVertical:7,alignItems:'center',minWidth:67},
  timeDate:{fontSize:10,color:Colors.light.textSecondary},
  timeText:{fontSize:15,fontWeight:'800'},
  loadingBox:{backgroundColor:'#fff',borderRadius:18,borderWidth:1,borderColor:Colors.light.border,padding:24,alignItems:'center',marginBottom:12},
  modalBackdrop:{flex:1,backgroundColor:'rgba(0,0,0,0.42)',justifyContent:'flex-end'},
  modalCard:{backgroundColor:Colors.light.background,borderTopLeftRadius:28,borderTopRightRadius:28,maxHeight:'94%',overflow:'hidden'},
  modalContent:{padding:18,paddingBottom:36},
  modalHeader:{flexDirection:'row',alignItems:'center',gap:10,marginBottom:12},
  modalHeaderTitle:{flex:1,fontSize:22,lineHeight:28},
  closeButton:{backgroundColor:Colors.light.primary,borderRadius:12,paddingHorizontal:13,paddingVertical:9},
  closeText:{color:'#fff',fontWeight:'800'},
  poster:{width:'100%',height:360,borderRadius:18,backgroundColor:'#E8E8E8',marginBottom:18},
  posterPlaceholder:{height:240,borderRadius:18,backgroundColor:'#E8EEE9',alignItems:'center',justifyContent:'center',marginBottom:18},
  modalTitle:{marginBottom:4},
  originalTitle:{marginBottom:14},
  metadataGrid:{flexDirection:'row',gap:8,flexWrap:'wrap',marginBottom:10},
  infoBox:{flexGrow:1,minWidth:105,backgroundColor:'#fff',borderWidth:1,borderColor:Colors.light.border,borderRadius:14,padding:11},
  infoValue:{fontWeight:'800',marginTop:2},
  infoLine:{backgroundColor:'#fff',borderWidth:1,borderColor:Colors.light.border,borderRadius:14,padding:12,marginTop:8},
  infoLineValue:{marginTop:3,lineHeight:21},
  section:{marginTop:20},
  sectionTitle:{fontSize:23,lineHeight:29,marginBottom:8},
  synopsis:{lineHeight:22},
  modalVariant:{backgroundColor:'#fff',borderWidth:1,borderColor:Colors.light.border,borderRadius:14,padding:12,marginTop:8},
  infoLink:{backgroundColor:Colors.light.primary,borderRadius:14,padding:14,alignItems:'center',marginTop:20},
  infoLinkText:{color:'#fff',fontWeight:'800'},
});
