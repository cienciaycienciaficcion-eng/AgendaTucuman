import { useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { EventCard } from '@/components/event-card';
import { EventDetailsModal } from '@/components/event-details-modal';
import { ThemedText } from '@/components/themed-text';
import { Colors, MaxContentWidth, Spacing } from '@/constants/theme';
import { eventEffectiveEndDate, formatDate, isServiceEvent, todayIso } from '@/data';
import { useAgendaData } from '@/data/use-remote-data';

function monthDays(year: number, month: number) {
  const first = new Date(year, month, 1);
  const count = new Date(year, month + 1, 0).getDate();
  const offset = (first.getDay() + 6) % 7;
  return { count, offset };
}

export default function CalendarScreen() {
  const today = todayIso();
  const { events: agendaEvents } = useAgendaData();
  const now = new Date();
  const [selected, setSelected] = useState(today);
  const [month, setMonth] = useState(new Date(now.getFullYear(), now.getMonth(), 1));
  const [selectedEvent, setSelectedEvent] = useState<any | null>(null);

  const { count, offset } = monthDays(month.getFullYear(), month.getMonth());
  const cells = Array.from({ length: offset + count }, (_, i) => i < offset ? null : i - offset + 1);
  const visibleAgendaEvents = useMemo(() => agendaEvents.filter(e => !isServiceEvent(e)), [agendaEvents]);
  const daysWithEvents = useMemo(() => new Set(visibleAgendaEvents.flatMap(e => e.occurrences?.map((o: any) => o.date) ?? [e.date_start])), [visibleAgendaEvents]);
  const selectedEvents = visibleAgendaEvents.filter(e => e.date_start <= selected && eventEffectiveEndDate(e) >= selected).sort((a, b) => a.start_datetime.localeCompare(b.start_datetime));
  const monthName = month.toLocaleDateString('es-AR', { month: 'long', year: 'numeric' });

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.content}>
        <ThemedText type="title">Calendario</ThemedText>
        <ThemedText themeColor="textSecondary" style={styles.subtitle}>Elegí un día para ver qué hay.</ThemedText>
        <View style={styles.calendar}>
          <View style={styles.monthHeader}>
            <Pressable onPress={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))}><ThemedText type="title">‹</ThemedText></Pressable>
            <ThemedText type="subtitle" style={{ textTransform: 'capitalize' }}>{monthName}</ThemedText>
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
        {selectedEvents.length ? selectedEvents.map(e => <EventCard key={e.id} event={e} onPress={() => setSelectedEvent(e)} />) : <View style={styles.empty}><ThemedText>Sin eventos para este día.</ThemedText></View>}
      </ScrollView>
      <EventDetailsModal event={selectedEvent} visible={Boolean(selectedEvent)} onClose={() => setSelectedEvent(null)} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe:{flex:1,backgroundColor:Colors.light.background}, content:{width:'100%',maxWidth:MaxContentWidth,alignSelf:'center',paddingHorizontal:Spacing.three,paddingTop:12,paddingBottom:130}, subtitle:{marginTop:4,marginBottom:18}, calendar:{backgroundColor:Colors.light.backgroundElement,borderRadius:20,padding:16,borderWidth:1,borderColor:Colors.light.border}, monthHeader:{flexDirection:'row',justifyContent:'space-between',alignItems:'center',marginBottom:16}, week:{flexDirection:'row'}, weekday:{width:'14.285%',textAlign:'center',fontWeight:'800',color:Colors.light.textSecondary,fontSize:12}, grid:{flexDirection:'row',flexWrap:'wrap',marginTop:8}, cell:{width:'14.285%',aspectRatio:1,alignItems:'center',justifyContent:'center',borderRadius:12}, cellActive:{backgroundColor:Colors.light.primary}, activeText:{color:'#fff',fontWeight:'800'}, dot:{width:5,height:5,borderRadius:3,backgroundColor:Colors.light.primary,position:'absolute',bottom:7}, dotActive:{backgroundColor:'#fff'}, section:{marginTop:22,marginBottom:12,textTransform:'capitalize'}, empty:{backgroundColor:Colors.light.backgroundElement,borderRadius:16,padding:24,borderWidth:1,borderColor:Colors.light.border},
});
