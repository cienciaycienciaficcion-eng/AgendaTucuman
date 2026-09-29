import { useMemo, useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { EventCard } from '@/components/event-card';
import { ThemedText } from '@/components/themed-text';
import { Colors, Spacing, MaxContentWidth } from '@/constants/theme';
import { formatDate } from '@/data';
import { useAgendaData } from '@/data/use-remote-data';

const filters = ['Todos', 'Música', 'Teatro', 'Variedades', 'Talleres y Cursos'];

export default function AgendaScreen() {
  const { events: agendaEvents, loading, online, refresh } = useAgendaData();
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('Todos');
  const today = (() => {
    const d = new Date();
    const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
    return local.toISOString().slice(0, 10);
  })();

  const events = useMemo(() => {
    return [...agendaEvents]
      .filter(e => e.date_end >= today)
      .filter(e => filter === 'Todos' || e.categories?.includes(filter))
      .filter(e => !query.trim() || `${e.title} ${e.location} ${e.description}`.toLowerCase().includes(query.toLowerCase()))
      .sort((a, b) => a.start_datetime.localeCompare(b.start_datetime));
  }, [agendaEvents, query, filter, today]);

  const openEvent = (event: any) => {
    const lines = [
      formatDate(event.date_start),
      event.time_start ? `Horario: ${event.time_start}${event.time_end ? ` - ${event.time_end}` : ''}` : '',
      event.location ? `Lugar: ${event.location}` : '',
      event.address ? `Dirección: ${event.address}` : '',
      event.is_free ? 'Entrada libre y gratuita' : '',
    ].filter(Boolean);
    Alert.alert(event.title.replace(/^\d{1,2} de [A-Za-z]+\\|\\s*/i, ''), lines.join('\n'));
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <View>
            <ThemedText type="small" themeColor="textSecondary">TUCUMÁN</ThemedText>
            <ThemedText type="title">Agenda</ThemedText>
            <ThemedText themeColor="textSecondary">Qué hacer y dónde ir</ThemedText>
          </View>
          <View style={styles.count}>
            <ThemedText style={styles.countNumber}>{events.length}</ThemedText>
            <ThemedText style={styles.countLabel}>eventos</ThemedText>
          </View>
        </View>

        <TextInput
          value={query}
          onChangeText={setQuery}
          placeholder="Buscar eventos, lugares..."
          placeholderTextColor="#87948D"
          style={styles.search}
        />

        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filters}>
          {filters.map(item => (
            <Pressable
              key={item}
              onPress={() => setFilter(item)}
              style={[styles.filter, filter === item && styles.filterActive]}>
              <ThemedText style={filter === item ? styles.filterTextActive : undefined}>
                {item}
              </ThemedText>
            </Pressable>
          ))}
        </ScrollView>

        <View style={styles.statusRow}>
          <ThemedText themeColor="textSecondary">
            {loading ? 'Actualizando…' : online ? 'Datos actualizados desde GitHub' : 'Sin conexión · usando datos guardados'}
          </ThemedText>
          <Pressable onPress={refresh} style={styles.refreshButton}>
            <ThemedText style={styles.refreshText}>Actualizar</ThemedText>
          </Pressable>
        </View>

        <ThemedText type="subtitle" style={styles.sectionTitle}>
          Próximos eventos
        </ThemedText>

        {events.length === 0 ? (
          <View style={styles.empty}>
            <ThemedText type="subtitle">No encontramos eventos</ThemedText>
            <ThemedText themeColor="textSecondary">Probá con otro filtro o búsqueda.</ThemedText>
          </View>
        ) : (
          events.map(event => (
            <EventCard key={event.id} event={event} onPress={() => openEvent(event)} />
          ))
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.light.background },
  content: { width: '100%', maxWidth: MaxContentWidth, alignSelf: 'center', padding: Spacing.three, paddingBottom: 110 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: Spacing.three },
  count: { backgroundColor: '#DDEFE5', borderRadius: 16, paddingHorizontal: 14, paddingVertical: 9, alignItems: 'center' },
  countNumber: { color: Colors.light.primaryDark, fontSize: 22, fontWeight: '800' },
  countLabel: { color: Colors.light.primaryDark, fontSize: 11 },
  search: { backgroundColor: '#fff', borderColor: Colors.light.border, borderWidth: 1, borderRadius: 14, paddingHorizontal: 16, paddingVertical: 12, fontSize: 15, marginBottom: 12 },
  filters: { gap: 8, paddingBottom: 8 },
  filter: { borderWidth: 1, borderColor: Colors.light.border, borderRadius: 20, paddingHorizontal: 13, paddingVertical: 8, backgroundColor: '#fff' },
  filterActive: { backgroundColor: Colors.light.primary, borderColor: Colors.light.primary },
  filterTextActive: { color: '#fff', fontWeight: '700' },
  statusRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 10, marginBottom: 2 },
  refreshButton: { borderWidth: 1, borderColor: Colors.light.border, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 6, backgroundColor: '#fff' },
  refreshText: { color: Colors.light.primaryDark, fontWeight: '700', fontSize: 12 },
  sectionTitle: { marginTop: 16, marginBottom: 12 },
  empty: { padding: 32, borderRadius: 18, backgroundColor: '#fff', alignItems: 'center', gap: 8 },
});
