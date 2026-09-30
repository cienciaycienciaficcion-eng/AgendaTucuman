import { useMemo, useState } from 'react';
import { Image, Linking, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { ThemedText } from '@/components/themed-text';
import { Colors, MaxContentWidth, Spacing } from '@/constants/theme';
import { todayIso } from '@/data';
import { useCinemaData, useMovieInfoData } from '@/data/use-remote-data';

function normalizeTitle(value: string) {
  return (value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

function formatReleaseDate(value: string | null) {
  if (!value) return '';
  const parts = value.split('-');
  if (parts.length !== 3) return value;
  return `${parts[2]}/${parts[1]}/${parts[0]}`;
}

export default function CineScreen() {
  const today = todayIso();
  const { data: cinemaData, loading, online, refresh } = useCinemaData();
  const { data: movieInfoData } = useMovieInfoData();
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const infoByTitle = useMemo(() => {
    const map: Record<string, any> = {};
    for (const movie of movieInfoData?.peliculas || []) {
      const key = normalizeTitle(movie.titulo_cinemacenter || movie.titulo);
      if (key) map[key] = movie;
    }
    return map;
  }, [movieInfoData]);

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
  }, [cinemaData, today]);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <View style={{ flex: 1 }}>
            <ThemedText type="title">Cine</ThemedText>
            <ThemedText themeColor="textSecondary">
              Cinemacenter Tucumán · {cinemaData.cartelera.week_start} al {cinemaData.cartelera.week_end}
            </ThemedText>
          </View>
          <Pressable
            onPress={() => Linking.openURL('https://www.cinemacenter.com.ar/cartelera#contenido')}
            style={styles.source}
          >
            <ThemedText style={styles.sourceText}>Sitio oficial</ThemedText>
          </Pressable>
        </View>

        <View style={styles.statusRow}>
          <ThemedText themeColor="textSecondary">
            {loading ? 'Actualizando cartelera…' : online ? 'Cartelera actualizada desde GitHub' : 'Sin conexión · cartelera guardada'}
          </ThemedText>
          <Pressable onPress={refresh} style={styles.refreshButton}>
            <ThemedText style={styles.refreshText}>Actualizar</ThemedText>
          </Pressable>
        </View>

        {movies.map((movie: any) => {
          const info = infoByTitle[normalizeTitle(movie.title)];
          const isExpanded = !!expanded[movie.title];

          return (
            <View key={movie.title} style={styles.card}>
              <View style={styles.movieTop}>
                {info?.poster ? (
                  <Image source={{ uri: info.poster }} style={styles.poster} resizeMode="cover" />
                ) : (
                  <View style={styles.posterPlaceholder}>
                    <ThemedText style={styles.posterPlaceholderText}>SIN PÓSTER</ThemedText>
                  </View>
                )}

                <View style={styles.movieSummary}>
                  <ThemedText type="subtitle">{info?.titulo || movie.title}</ThemedText>

                  {!!info?.titulo_original && info.titulo_original !== info.titulo && (
                    <ThemedText style={styles.originalTitle}>{info.titulo_original}</ThemedText>
                  )}

                  <View style={styles.metaRow}>
                    {info?.anio ? <ThemedText themeColor="textSecondary">{info.anio}</ThemedText> : null}
                    {info?.duracion_minutos ? (
                      <ThemedText themeColor="textSecondary">{info.duracion_minutos} min</ThemedText>
                    ) : null}
                  </View>

                  {!!info?.generos?.length && (
                    <ThemedText style={styles.genres}>
                      {info.generos.join(' · ')}
                    </ThemedText>
                  )}
                </View>
              </View>

              {info?.sinopsis ? (
                <View style={styles.synopsisBox}>
                  <ThemedText style={styles.sectionTitle}>Sinopsis</ThemedText>
                  <ThemedText themeColor="textSecondary">{info.sinopsis}</ThemedText>
                </View>
              ) : null}

              {isExpanded && info ? (
                <View style={styles.details}>
                  {!!info.fecha_estreno && (
                    <View style={styles.detailLine}>
                      <ThemedText style={styles.detailLabel}>Estreno</ThemedText>
                      <ThemedText>{formatReleaseDate(info.fecha_estreno)}</ThemedText>
                    </View>
                  )}

                  {!!info.director?.length && (
                    <View style={styles.detailLine}>
                      <ThemedText style={styles.detailLabel}>Director</ThemedText>
                      <ThemedText>{info.director.join(', ')}</ThemedText>
                    </View>
                  )}

                  {!!info.actores?.length && (
                    <View style={styles.detailLine}>
                      <ThemedText style={styles.detailLabel}>Actores</ThemedText>
                      <ThemedText>
                        {info.actores.map((actor: any) => actor.nombre).join(', ')}
                      </ThemedText>
                    </View>
                  )}

                  {!!info.trailers?.length && (
                    <View style={styles.trailerSection}>
                      <ThemedText style={styles.sectionTitle}>Tráilers</ThemedText>
                      {info.trailers.map((trailer: any) => (
                        <Pressable
                          key={trailer.youtube_id}
                          onPress={() => Linking.openURL(trailer.url)}
                          style={styles.trailerButton}
                        >
                          <ThemedText style={styles.trailerText}>▶ {trailer.titulo}</ThemedText>
                        </Pressable>
                      ))}
                    </View>
                  )}
                </View>
              ) : null}

              {info && (
                <Pressable
                  onPress={() => setExpanded(prev => ({ ...prev, [movie.title]: !isExpanded }))}
                  style={styles.moreButton}
                >
                  <ThemedText style={styles.moreText}>
                    {isExpanded ? 'Ocultar información' : 'Ver director, actores y tráilers'}
                  </ThemedText>
                </Pressable>
              )}

              {movie.variants.map((variant: any) => (
                <View key={variant.id} style={styles.variant}>
                  <View style={styles.badges}>
                    <View style={styles.badge}>
                      <ThemedText style={styles.badgeText}>{variant.format}</ThemedText>
                    </View>
                    <View style={[styles.badge, styles.badgeSecondary]}>
                      <ThemedText style={styles.badgeText}>{variant.language}</ThemedText>
                    </View>
                  </View>

                  <View style={styles.times}>
                    {variant.occurrences
                      .filter((o: any) => o.date >= today)
                      .slice(0, 12)
                      .map((o: any) => (
                        <View key={o.datetime} style={styles.time}>
                          <ThemedText style={styles.timeDate}>
                            {o.date.slice(8, 10)}/{o.date.slice(5, 7)}
                          </ThemedText>
                          <ThemedText style={styles.timeText}>{o.time}</ThemedText>
                        </View>
                      ))}
                  </View>
                </View>
              ))}
            </View>
          );
        })}

        <View style={styles.note}>
          <ThemedText style={styles.noteTitle}>Información de películas</ThemedText>
          <ThemedText themeColor="textSecondary">
            Los horarios provienen de Cinemacenter. Los datos de películas, cuando están disponibles,
            se actualizan automáticamente desde GitHub.
          </ThemedText>
          <ThemedText style={styles.tmdbNotice}>
            This product uses the TMDB API but is not endorsed or certified by TMDB.
          </ThemedText>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.light.background },
  content: { width: '100%', maxWidth: MaxContentWidth, alignSelf: 'center', padding: Spacing.three, paddingBottom: 110 },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 18 },
  source: { backgroundColor: Colors.light.primary, borderRadius: 14, paddingHorizontal: 12, paddingVertical: 9 },
  sourceText: { color: '#fff', fontWeight: '700', fontSize: 12 },
  card: { backgroundColor: '#fff', borderWidth: 1, borderColor: Colors.light.border, borderRadius: 18, padding: 16, marginBottom: 12 },
  movieTop: { flexDirection: 'row', gap: 14 },
  poster: { width: 94, height: 140, borderRadius: 10, backgroundColor: '#E9EFEB' },
  posterPlaceholder: { width: 94, height: 140, borderRadius: 10, backgroundColor: '#E9EFEB', alignItems: 'center', justifyContent: 'center', padding: 8 },
  posterPlaceholderText: { fontSize: 10, fontWeight: '800', color: Colors.light.textSecondary, textAlign: 'center' },
  movieSummary: { flex: 1, paddingTop: 2 },
  originalTitle: { fontSize: 12, fontStyle: 'italic', marginTop: 4, color: Colors.light.textSecondary },
  metaRow: { flexDirection: 'row', gap: 10, marginTop: 9 },
  genres: { fontSize: 12, marginTop: 7, color: Colors.light.primaryDark },
  synopsisBox: { marginTop: 14, paddingTop: 13, borderTopWidth: 1, borderTopColor: '#E9EFEB' },
  sectionTitle: { fontWeight: '800', marginBottom: 5, color: Colors.light.primaryDark },
  details: { marginTop: 13, paddingTop: 13, borderTopWidth: 1, borderTopColor: '#E9EFEB', gap: 10 },
  detailLine: { gap: 3 },
  detailLabel: { fontSize: 12, fontWeight: '800', color: Colors.light.primaryDark },
  trailerSection: { marginTop: 2 },
  trailerButton: { borderWidth: 1, borderColor: Colors.light.border, borderRadius: 10, paddingHorizontal: 11, paddingVertical: 9, marginTop: 6 },
  trailerText: { color: Colors.light.primaryDark, fontWeight: '700', fontSize: 12 },
  moreButton: { marginTop: 12, alignSelf: 'flex-start' },
  moreText: { color: Colors.light.primaryDark, fontWeight: '800', fontSize: 12 },
  variant: { marginTop: 12, paddingTop: 12, borderTopWidth: 1, borderTopColor: '#E9EFEB' },
  badges: { flexDirection: 'row', gap: 6, marginBottom: 10 },
  badge: { backgroundColor: Colors.light.primary, borderRadius: 7, paddingHorizontal: 8, paddingVertical: 4 },
  badgeSecondary: { backgroundColor: Colors.light.primaryDark },
  badgeText: { color: '#fff', fontSize: 11, fontWeight: '800' },
  times: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  time: { borderWidth: 1, borderColor: Colors.light.border, borderRadius: 10, paddingHorizontal: 9, paddingVertical: 7, alignItems: 'center', minWidth: 67 },
  timeDate: { fontSize: 10, color: Colors.light.textSecondary },
  timeText: { fontSize: 15, fontWeight: '800' },
  note: { backgroundColor: '#EAF5EE', borderRadius: 16, padding: 16, marginTop: 4 },
  noteTitle: { fontWeight: '800', marginBottom: 4, color: Colors.light.primaryDark },
  tmdbNotice: { fontSize: 10, marginTop: 10, color: Colors.light.textSecondary },
  statusRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, gap: 8 },
  refreshButton: { borderWidth: 1, borderColor: Colors.light.border, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 6, backgroundColor: '#fff' },
  refreshText: { color: Colors.light.primaryDark, fontWeight: '700', fontSize: 12 },
});
