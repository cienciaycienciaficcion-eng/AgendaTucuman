import { Pressable, StyleSheet, View } from 'react-native';
import { ThemedText } from './themed-text';
import { Colors, Spacing } from '@/constants/theme';
import { formatDate } from '@/data';

type Props = {
  event: any;
  onPress?: () => void;
};

export function EventCard({ event, onPress }: Props) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [styles.card, pressed && styles.pressed]}>
      <View style={styles.dateBox}>
        <ThemedText style={styles.day}>{event.date_start.slice(8, 10)}</ThemedText>
        <ThemedText style={styles.month}>
          {formatDate(event.date_start).split(' ')[2]?.slice(0, 3).toUpperCase()}
        </ThemedText>
      </View>

      <View style={styles.body}>
        <ThemedText type="smallBold" style={styles.category}>
          {event.categories?.[0] ?? 'Evento'}
        </ThemedText>
        <ThemedText type="subtitle" numberOfLines={2}>{event.title}</ThemedText>

        <ThemedText themeColor="textSecondary" numberOfLines={1}>
          {event.time_start ? `🕐 ${event.time_start}` : ''}
          {event.location ? `   ·   📍 ${event.location}` : ''}
        </ThemedText>

        {event.is_free && (
          <View style={styles.free}>
            <ThemedText style={styles.freeText}>Entrada libre</ThemedText>
          </View>
        )}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    backgroundColor: Colors.light.backgroundElement,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: Colors.light.border,
    padding: Spacing.three,
    gap: Spacing.three,
    marginBottom: Spacing.two,
  },
  pressed: { opacity: 0.75, transform: [{ scale: 0.99 }] },
  dateBox: {
    width: 58,
    height: 64,
    borderRadius: 14,
    backgroundColor: Colors.light.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  day: { color: '#fff', fontSize: 24, fontWeight: '800', lineHeight: 26 },
  month: { color: '#fff', fontSize: 11, fontWeight: '800' },
  body: { flex: 1, gap: 5 },
  category: { color: Colors.light.primary, textTransform: 'uppercase' },
  free: {
    alignSelf: 'flex-start',
    backgroundColor: '#E2F4E9',
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  freeText: { color: Colors.light.primaryDark, fontSize: 11, fontWeight: '700' },
});
