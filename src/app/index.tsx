import { useEffect, useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { EventCard } from '@/components/event-card';
import { EventCalendar } from '@/components/event-calendar';
import { EventDetailsModal } from '@/components/event-details-modal';
import { ThemedText } from '@/components/themed-text';
import { Colors, Spacing, MaxContentWidth } from '@/constants/theme';
import { eventCategories, eventIsActiveOrUpcoming, isServiceEvent, normalizeSearchText } from '@/data';
import { useAgendaData } from '@/data/use-remote-data';

const DEFAULT_FILTERS = ['Todos', 'Música', 'Teatro', 'Variedades', 'Talleres y Cursos'];

export default function AgendaScreen() {
  const { events: agendaEvents } = useAgendaData();
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('Todos');
  const [selectedEvent, setSelectedEvent] = useState<any | null>(null);
  const today = (() => {
    const d = new Date();
    const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
    return local.toISOString().slice(0, 10);
  })();

  const filters = useMemo(() => {
    // Servicios tienen su propia sección y no deben aparecer como filtro
    // dentro de la Agenda general.
    const agendaOnlyEvents = agendaEvents.filter(event => !isServiceEvent(event));
    const discovered = agendaOnlyEvents.flatMap(eventCategories)
      .map(value => String(value).trim())
      .filter(Boolean);

    const canonical = new Map<string, string>();
    [...DEFAULT_FILTERS.slice(1), ...discovered].forEach(category => {
      const key = normalizeSearchText(category);
      if (!key || key === 'todos') return;
      if (!canonical.has(key)) canonical.set(key, category);
    });

    const preferred = DEFAULT_FILTERS.slice(1).filter(category => canonical.has(normalizeSearchText(category)))
      .map(category => canonical.get(normalizeSearchText(category))!);
    const extra = [...canonical.entries()]
      .filter(([key]) => !DEFAULT_FILTERS.slice(1).some(category => normalizeSearchText(category) === key))
      .map(([, label]) => label)
      .sort((a, b) => a.localeCompare(b, 'es'));

    return ['Todos', ...preferred, ...extra];
  }, [agendaEvents]);

  const events = useMemo(() => {
    const wanted = normalizeSearchText(filter);

    return [...agendaEvents]
      .filter(e => eventIsActiveOrUpcoming(e, today))
      .filter(e => !isServiceEvent(e))
      .filter(e => filter === 'Todos' || eventCategories(e).some(c => normalizeSearchText(c) === wanted))
      .filter(e => !query.trim() || `${e.title} ${e.location} ${e.address} ${e.description} ${eventCategories(e).join(' ')}`.toLowerCase().includes(query.toLowerCase()))
      .sort((a, b) => a.start_datetime.localeCompare(b.start_datetime));
  }, [agendaEvents, query, filter, today]);

  useEffect(() => {
    if (filter !== 'Todos' && !filters.some(item => normalizeSearchText(item) === normalizeSearchText(filter))) {
      setFilter('Todos');
    }
  }, [filters, filter]);

  return (
    <SafeAreaView style={styles.safe}>
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
            <Pressable key={item} onPress={() => setFilter(item)} style={[styles.filter, filter === item && styles.filterActive]}>
              <ThemedText style={filter === item ? styles.filterTextActive : undefined}>{item}</ThemedText>
            </Pressable>
          ))}
        </ScrollView>

        <View style={styles.calendarSection}>
          <EventCalendar
            events={events}
            today={today}
            title="Calendario de Agenda"
            subtitle="Consultá por fecha y por tema."
            topicLabel="Temas de la agenda"
          />
        </View>

        <ThemedText type="subtitle" style={styles.sectionTitle}>Próximos eventos</ThemedText>

        {events.length === 0 ? (
          <View style={styles.empty}>
            <ThemedText type="subtitle">No encontramos eventos</ThemedText>
            <ThemedText themeColor="textSecondary">Probá con otro filtro o búsqueda.</ThemedText>
          </View>
        ) : events.map(event => (
          <EventCard key={event.id} event={event} onPress={() => setSelectedEvent(event)} />
        ))}
      </ScrollView>

      <EventDetailsModal event={selectedEvent} visible={Boolean(selectedEvent)} onClose={() => setSelectedEvent(null)} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.light.background },
  content: { width: '100%', maxWidth: MaxContentWidth, alignSelf: 'center', paddingHorizontal: Spacing.three, paddingTop: 12, paddingBottom: 110 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: Spacing.three },
  count: { backgroundColor: Colors.light.backgroundSelected, borderRadius: 16, paddingHorizontal: 14, paddingVertical: 9, alignItems: 'center' },
  countNumber: { color: Colors.light.primaryDark, fontSize: 22, fontWeight: '800' },
  countLabel: { color: Colors.light.primaryDark, fontSize: 11 },
  search: { color: Colors.light.text, backgroundColor: Colors.light.backgroundElement, borderColor: Colors.light.border, borderWidth: 1, borderRadius: 14, paddingHorizontal: 16, paddingVertical: 12, fontSize: 15, marginBottom: 12 },
  filters: { gap: 8, paddingBottom: 8 },
  filter: { borderWidth: 1, borderColor: Colors.light.border, borderRadius: 20, paddingHorizontal: 13, paddingVertical: 8, backgroundColor: Colors.light.backgroundElement },
  filterActive: { backgroundColor: Colors.light.primary, borderColor: Colors.light.primary },
  filterTextActive: { color: '#fff', fontWeight: '700' },
  sectionTitle: { marginTop: 16, marginBottom: 12 },
  calendarSection: { marginTop: 18, marginBottom: 8 },
  empty: { padding: 32, borderRadius: 18, backgroundColor: Colors.light.backgroundElement, alignItems: 'center', gap: 8 },
});
