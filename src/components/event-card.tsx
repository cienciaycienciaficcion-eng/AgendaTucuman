import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { Image } from 'expo-image';
import { ThemedText } from './themed-text';
import { Colors, Spacing } from '@/constants/theme';
import { formatDate } from '@/data';

type Props = {
  event: any;
  onPress?: () => void;
};

export function EventCard({ event, onPress }: Props) {
  const [imageError, setImageError] = useState(false);
  const hasImage = Boolean(event.image && !imageError);

  return (
    <Pressable onPress={onPress} style={({ pressed }) => [styles.card, pressed && styles.pressed]}>
      {hasImage && (
        <Image
          source={{ uri: event.image }}
          style={styles.image}
          contentFit="cover"
          cachePolicy="memory-disk"
          transition={150}
          onError={() => setImageError(true)}
          accessibilityLabel={`Imagen de ${event.title}`}
        />
      )}

      <View style={styles.eventRow}>
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
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: Colors.light.backgroundElement,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: Colors.light.border,
    padding: Spacing.three,
    marginBottom: Spacing.two,
    overflow: 'hidden',
  },
  pressed: { opacity: 0.75, transform: [{ scale: 0.99 }] },
  image: {
    width: '100%',
    height: 180,
    borderRadius: 14,
    marginBottom: Spacing.three,
    backgroundColor: '#E8E8E8',
  },
  eventRow: {
    flexDirection: 'row',
    gap: Spacing.three,
  },
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
  category: { color: Colors.light.primaryDark, textTransform: 'uppercase', fontWeight: '800' },
  free: {
    alignSelf: 'flex-start',
    backgroundColor: '#E2F4E9',
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  freeText: { color: Colors.light.primaryDark, fontSize: 11, fontWeight: '700' },
});
