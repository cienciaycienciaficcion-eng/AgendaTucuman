import { useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { EventCard } from '@/components/event-card';
import { EventCalendar } from '@/components/event-calendar';
import { EventDetailsModal } from '@/components/event-details-modal';
import { ThemedText } from '@/components/themed-text';
import { eventCategories, eventIsActiveOrUpcoming, isServiceEvent, normalizeSearchText, todayIso } from '@/data';
import { Colors, MaxContentWidth, Spacing } from '@/constants/theme';
import { useServicesData } from '@/data/use-remote-data';

export default function ServicesScreen() {
  const { events: serviceEvents } = useServicesData();
  const [query, setQuery] = useState('');
  const [selectedEvent, setSelectedEvent] = useState<any | null>(null);
  const today = todayIso();

  const events = useMemo(() => {
    const q = normalizeSearchText(query);
    return [...serviceEvents]
      .filter(event => eventIsActiveOrUpcoming(event, today))
      .filter(event => isServiceEvent(event))
      .filter(event => !q || normalizeSearchText([
        event.title,
        event.location,
        event.address,
        event.description,
        ...eventCategories(event),
      ].join(' ')).includes(q))
      .sort((a, b) => a.start_datetime.localeCompare(b.start_datetime));
  }, [serviceEvents, query, today]);

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.content}>
        <ThemedText type="small" themeColor="textSecondary">TUCUMÁN</ThemedText>
        <ThemedText type="title">Servicios</ThemedText>
        <ThemedText themeColor="textSecondary" style={styles.subtitle}>
          Trámites, servicios y propuestas útiles.
        </ThemedText>

        <TextInput
          value={query}
          onChangeText={setQuery}
          placeholder="Buscar servicios..."
          placeholderTextColor="#87948D"
          style={styles.search}
        />

        <View style={styles.calendarSection}>
          <EventCalendar
            events={events}
            today={today}
            title="Calendario de Servicios"
            subtitle="Consultá trámites, servicios y actividades por fecha."
            topicLabel="Temas de servicios"
          />
        </View>

        <ThemedText type="subtitle" style={styles.sectionTitle}>
          {events.length} servicio{events.length === 1 ? '' : 's'}
        </ThemedText>

        {events.length === 0 ? (
          <View style={styles.empty}>
            <ThemedText type="subtitle">No encontramos servicios</ThemedText>
            <ThemedText themeColor="textSecondary">Probá con otra búsqueda.</ThemedText>
          </View>
        ) : events.map(event => (
          <EventCard key={event.id} event={event} onPress={() => setSelectedEvent(event)} />
        ))}
      </ScrollView>

      <EventDetailsModal
        event={selectedEvent}
        visible={Boolean(selectedEvent)}
        onClose={() => setSelectedEvent(null)}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe:{flex:1,backgroundColor:Colors.light.background},
  content:{width:'100%',maxWidth:MaxContentWidth,alignSelf:'center',paddingHorizontal:Spacing.three,paddingTop:12,paddingBottom:130},
  subtitle:{marginTop:5,marginBottom:18},
  search:{color:Colors.light.text,backgroundColor:Colors.light.backgroundElement,borderColor:Colors.light.border,borderWidth:1,borderRadius:14,paddingHorizontal:16,paddingVertical:12,fontSize:15,marginBottom:12},
  calendarSection:{marginTop:8,marginBottom:18},
  sectionTitle:{marginTop:8,marginBottom:12},
  empty:{padding:32,borderRadius:18,backgroundColor:Colors.light.backgroundElement,alignItems:'center',gap:8},
});
