import { useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { EventCard } from '@/components/event-card';
import { EventDetailsModal } from '@/components/event-details-modal';
import { ThemedText } from '@/components/themed-text';
import { Colors } from '@/constants/theme';
import { eventCategories, eventEffectiveEndDate, formatDate, normalizeSearchText } from '@/data';

function monthDays(year: number, month: number) {
  const first = new Date(year, month, 1);
  const count = new Date(year, month + 1, 0).getDate();
  const offset = (first.getDay() + 6) % 7;
  return { count, offset };
}

export function EventCalendar({
  events,
  today,
  title = 'Calendario',
  subtitle = 'Elegí un día para ver qué hay.',
  topicLabel = 'Temas',
}: {
  events: any[];
  today: string;
  title?: string;
  subtitle?: string;
  topicLabel?: string;
}) {
  const now = new Date();
  const [selected, setSelected] = useState(today);
  const [month, setMonth] = useState(new Date(now.getFullYear(), now.getMonth(), 1));
  const [topic, setTopic] = useState('Todos');
  const [selectedEvent, setSelectedEvent] = useState<any | null>(null);

  const topics = useMemo(() => {
    const map = new Map<string, string>();
    events.flatMap(eventCategories).forEach(value => {
      const label = String(value).trim();
      const key = normalizeSearchText(label);
      if (key && !map.has(key)) map.set(key, label);
    });
    return ['Todos', ...[...map.values()].sort((a, b) => a.localeCompare(b, 'es'))];
  }, [events]);

  const filtered = useMemo(() => {
    if (topic === 'Todos') return events;
    const wanted = normalizeSearchText(topic);
    return events.filter(event => eventCategories(event).some(c => normalizeSearchText(c) === wanted));
  }, [events, topic]);

  const { count, offset } = monthDays(month.getFullYear(), month.getMonth());
  const cells = Array.from({ length: offset + count }, (_, i) => i < offset ? null : i - offset + 1);
  const daysWithEvents = useMemo(
    () => new Set(filtered.flatMap(e => e.occurrences?.map((o: any) => o.date) ?? [e.date_start])),
    [filtered]
  );
  const selectedEvents = filtered
    .filter(e => e.date_start <= selected && eventEffectiveEndDate(e) >= selected)
    .sort((a, b) => a.start_datetime.localeCompare(b.start_datetime));
  const monthName = month.toLocaleDateString('es-AR', { month: 'long', year: 'numeric' });

  return (
    <View>
      <ThemedText type="subtitle">{title}</ThemedText>
      <ThemedText themeColor="textSecondary" style={styles.subtitle}>{subtitle}</ThemedText>

      {topics.length > 1 ? (
        <>
          <ThemedText type="smallBold" themeColor="textSecondary" style={styles.topicLabel}>{topicLabel}</ThemedText>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.topics}>
            {topics.map(item => (
              <Pressable key={item} onPress={() => setTopic(item)} style={[styles.topic, topic === item && styles.topicActive]}>
                <ThemedText style={topic === item ? styles.topicTextActive : undefined}>{item}</ThemedText>
              </Pressable>
            ))}
          </ScrollView>
        </>
      ) : null}

      <View style={styles.calendar}>
        <View style={styles.monthHeader}>
          <Pressable onPress={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))}><ThemedText type="title">‹</ThemedText></Pressable>
          <ThemedText type="subtitle" style={styles.monthName}>{monthName}</ThemedText>
          <Pressable onPress={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))}><ThemedText type="title">›</ThemedText></Pressable>
        </View>
        <View style={styles.week}>{['L','M','M','J','V','S','D'].map((d, i) => <ThemedText key={i} style={styles.weekday}>{d}</ThemedText>)}</View>
        <View style={styles.grid}>
          {cells.map((day, i) => {
            if (!day) return <View key={i} style={styles.cell} />;
            const iso = `${month.getFullYear()}-${String(month.getMonth()+1).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
            const active = iso === selected;
            const has = daysWithEvents.has(iso);
            return <Pressable key={i} onPress={() => setSelected(iso)} style={[styles.cell, active && styles.cellActive]}>
              <ThemedText style={active ? styles.activeText : undefined}>{day}</ThemedText>
              {has && <View style={[styles.dot, active && styles.dotActive]} />}
            </Pressable>;
          })}
        </View>
      </View>

      <ThemedText type="subtitle" style={styles.section}>{selected === today ? 'Hoy' : formatDate(selected)}</ThemedText>
      {selectedEvents.length ? selectedEvents.map(e => <EventCard key={e.id} event={e} onPress={() => setSelectedEvent(e)} />) : <View style={styles.empty}><ThemedText>Sin resultados para este día.</ThemedText></View>}

      <EventDetailsModal event={selectedEvent} visible={Boolean(selectedEvent)} onClose={() => setSelectedEvent(null)} />
    </View>
  );
}

const styles = StyleSheet.create({
  subtitle:{marginTop:4,marginBottom:14},
  topicLabel:{marginBottom:7},
  topics:{gap:8,paddingBottom:12},
  topic:{borderWidth:1,borderColor:Colors.light.border,borderRadius:20,paddingHorizontal:12,paddingVertical:7,backgroundColor:Colors.light.backgroundElement},
  topicActive:{backgroundColor:Colors.light.primary,borderColor:Colors.light.primary},
  topicTextActive:{color:'#fff',fontWeight:'700'},
  calendar:{backgroundColor:Colors.light.backgroundElement,borderRadius:20,padding:16,borderWidth:1,borderColor:Colors.light.border},
  monthHeader:{flexDirection:'row',justifyContent:'space-between',alignItems:'center',marginBottom:16},
  monthName:{textTransform:'capitalize'},
  week:{flexDirection:'row'},
  weekday:{width:'14.285%',textAlign:'center',fontWeight:'800',color:Colors.light.textSecondary,fontSize:12},
  grid:{flexDirection:'row',flexWrap:'wrap',marginTop:8},
  cell:{width:'14.285%',aspectRatio:1,alignItems:'center',justifyContent:'center',borderRadius:12},
  cellActive:{backgroundColor:Colors.light.primary},
  activeText:{color:'#fff',fontWeight:'800'},
  dot:{width:5,height:5,borderRadius:3,backgroundColor:Colors.light.primary,position:'absolute',bottom:7},
  dotActive:{backgroundColor:'#fff'},
  section:{marginTop:18,marginBottom:10,textTransform:'capitalize'},
  empty:{backgroundColor:Colors.light.backgroundElement,borderRadius:16,padding:20,borderWidth:1,borderColor:Colors.light.border},
});
