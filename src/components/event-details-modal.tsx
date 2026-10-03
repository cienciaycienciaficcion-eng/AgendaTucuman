import { Linking, Modal, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { Image } from 'expo-image';
import { useState } from 'react';
import { Colors, MaxContentWidth, Spacing } from '@/constants/theme';
import { formatDate } from '@/data';
import { ThemedText } from './themed-text';

function cleanText(value: unknown) {
  return String(value ?? '')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/p>/gi, '\n\n')
    .replace(/<[^>]*>/g, '')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function googleCalendarUrl(event: any) {
  const title = cleanText(event.title).replace(/^\d{1,2} de [A-Za-zÁÉÍÓÚáéíóú]+\|\s*/i, '');
  const start = event.start_datetime ? new Date(event.start_datetime) : null;
  if (!start || Number.isNaN(start.getTime())) return '';

  let end = event.end_datetime ? new Date(event.end_datetime) : null;
  if (!end || Number.isNaN(end.getTime()) || end <= start) {
    end = new Date(start.getTime() + 2 * 60 * 60 * 1000);
  }

  const fmt = (d: Date) => d.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z');
  const details = cleanText(event.description);
  const location = [event.location, event.address, event.city].filter(Boolean).join(', ');
  return `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${encodeURIComponent(title)}&dates=${fmt(start)}/${fmt(end)}&details=${encodeURIComponent(details)}&location=${encodeURIComponent(location)}`;
}

function mapsUrl(event: any) {
  if (event.map_search_url) return event.map_search_url;
  const parts = [event.location, event.address, event.city].filter(Boolean);
  if (!parts.length && event.title) parts.push(event.title);
  parts.push('Tucumán');
  const query = parts.join(', ');
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`;
}

type Props = { event: any | null; visible: boolean; onClose: () => void };

export function EventDetailsModal({ event, visible, onClose }: Props) {
  const [imageError, setImageError] = useState(false);
  const [showDescription, setShowDescription] = useState(false);
  if (!event) return null;

  const title = cleanText(event.title).replace(/^\d{1,2} de [A-Za-zÁÉÍÓÚáéíóú]+\|\s*/i, '');
  const description = cleanText(event.description);
  const summary = cleanText(event.summary);
  const calendar = googleCalendarUrl(event);
  const maps = mapsUrl(event);
  const hasImage = Boolean(event.image && !imageError);
  const categories = Array.isArray(event.categories) ? event.categories : [];
  const tags = Array.isArray(event.tags) ? event.tags : [];

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <View style={styles.safe}>
        <View style={styles.topBar}>
          <ThemedText type="subtitle" numberOfLines={1} style={styles.topTitle}>{title}</ThemedText>
          <Pressable onPress={onClose} style={styles.close}><ThemedText style={styles.closeText}>×</ThemedText></Pressable>
        </View>
        <ScrollView contentContainerStyle={styles.content}>
          {hasImage && <Image source={{ uri: event.image }} style={styles.image} contentFit="cover" onError={() => setImageError(true)} />}

          <ThemedText type="title" style={styles.title}>{title}</ThemedText>

          <View style={styles.infoCard}>
            <ThemedText type="subtitle">📅 {formatDate(event.date_start)}{event.date_end && event.date_end !== event.date_start ? ` al ${formatDate(event.date_end)}` : ''}</ThemedText>
            {event.time_start ? <ThemedText themeColor="textSecondary">🕐 {event.time_start}{event.time_end ? ` – ${event.time_end}` : ''}</ThemedText> : null}
            {event.location ? <ThemedText themeColor="textSecondary">📍 {event.location}</ThemedText> : null}
            {event.address ? <ThemedText themeColor="textSecondary">{event.address}{event.city ? `, ${event.city}` : ''}</ThemedText> : null}
            {event.is_free ? <ThemedText style={styles.free}>Entrada libre y gratuita</ThemedText> : event.price != null ? <ThemedText style={styles.price}>Entrada: {event.price} {event.currency ?? ''}</ThemedText> : null}
            {event.organizer ? <ThemedText themeColor="textSecondary">Organiza: {event.organizer}</ThemedText> : null}
          </View>

          {categories.length > 0 && <View style={styles.tags}>{categories.map((c: string) => <View key={c} style={styles.tag}><ThemedText style={styles.tagText}>{c}</ThemedText></View>)}</View>}
          {tags.length > 0 && <View style={styles.tags}>{tags.map((t: string) => <View key={t} style={styles.tagSecondary}><ThemedText style={styles.tagSecondaryText}>{t}</ThemedText></View>)}</View>}

          {summary ? (
            <View style={styles.summaryCard}>
              <ThemedText type="subtitle" style={styles.summaryTitle}>Resumen</ThemedText>
              <ThemedText style={styles.summaryText}>{summary}</ThemedText>
              <Pressable onPress={() => setShowDescription((current) => !current)} style={styles.articleLink}>
                <ThemedText style={styles.articleLinkText}>{showDescription ? 'Ocultar artículo completo ↑' : 'Leer artículo completo ↓'}</ThemedText>
              </Pressable>
            </View>
          ) : null}

          {description && (!summary || showDescription) ? (
            <View style={styles.section}>
              <ThemedText type="subtitle">Descripción completa</ThemedText>
              <ThemedText style={styles.description}>{description}</ThemedText>
            </View>
          ) : null}

          <View style={styles.actions}>
            <Pressable onPress={() => Linking.openURL(calendar)} style={styles.primary} disabled={!calendar}>
              <ThemedText style={styles.primaryText}>＋ Agregar a Google Calendar</ThemedText>
            </Pressable>
            <Pressable onPress={() => Linking.openURL(maps)} style={styles.secondary} disabled={!maps}>
              <ThemedText style={styles.secondaryText}>📍 Cómo llegar con Google Maps</ThemedText>
            </Pressable>
            {event.url ? <Pressable onPress={() => Linking.openURL(event.url)} style={styles.secondary}><ThemedText style={styles.secondaryText}>Ver evento original</ThemedText></Pressable> : null}
            {Array.isArray(event.registration_urls) && event.registration_urls[0] ? <Pressable onPress={() => Linking.openURL(event.registration_urls[0])} style={styles.secondary}><ThemedText style={styles.secondaryText}>Inscripción / entradas</ThemedText></Pressable> : null}
          </View>
        </ScrollView>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.light.background },
  topBar: { minHeight: 72, paddingTop: 8, paddingHorizontal: Spacing.three, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', borderBottomWidth: 1, borderBottomColor: Colors.light.border, backgroundColor: Colors.light.backgroundElement },
  topTitle: { flex: 1, marginRight: 12 },
  close: { width: 42, height: 42, borderRadius: 21, backgroundColor: Colors.light.backgroundSelected, alignItems: 'center', justifyContent: 'center' },
  closeText: { fontSize: 30, lineHeight: 32, color: Colors.light.primaryDark },
  content: { width: '100%', maxWidth: MaxContentWidth, alignSelf: 'center', padding: Spacing.three, paddingBottom: 50 },
  image: { width: '100%', height: 230, borderRadius: 18, marginBottom: 18, backgroundColor: '#E8E8E8' },
  title: { marginBottom: 16 },
  infoCard: { backgroundColor: Colors.light.backgroundElement, borderRadius: 18, borderWidth: 1, borderColor: Colors.light.border, padding: 16, gap: 8 },
  free: { color: Colors.light.primaryDark, fontWeight: '800' },
  price: { color: Colors.light.primaryDark, fontWeight: '800' },
  tags: { flexDirection: 'row', flexWrap: 'wrap', gap: 7, marginTop: 12 },
  tag: { backgroundColor: Colors.light.primary, borderRadius: 14, paddingHorizontal: 10, paddingVertical: 5 },
  tagText: { color: '#fff', fontSize: 12, fontWeight: '800' },
  tagSecondary: { backgroundColor: Colors.light.backgroundSelected, borderRadius: 14, paddingHorizontal: 10, paddingVertical: 5 },
  tagSecondaryText: { color: Colors.light.primaryDark, fontSize: 12, fontWeight: '700' },
  section: { marginTop: 22, gap: 8 },
  summaryCard: { marginTop: 22, backgroundColor: Colors.light.backgroundSelected, borderRadius: 18, borderWidth: 1, borderColor: Colors.light.border, padding: 16, gap: 10 },
  summaryTitle: { color: Colors.light.primaryDark, fontWeight: '800' },
  summaryText: { lineHeight: 23, fontSize: 16 },
  articleLink: { alignSelf: 'flex-start', paddingVertical: 4 },
  articleLinkText: { color: Colors.light.primaryDark, fontWeight: '800', textDecorationLine: 'underline' },
  description: { lineHeight: 22 },
  actions: { marginTop: 24, gap: 10 },
  primary: { backgroundColor: Colors.light.primary, borderRadius: 15, padding: 15, alignItems: 'center' },
  primaryText: { color: '#fff', fontWeight: '800' },
  secondary: { backgroundColor: Colors.light.backgroundElement, borderWidth: 1, borderColor: Colors.light.border, borderRadius: 15, padding: 14, alignItems: 'center' },
  secondaryText: { color: Colors.light.primaryDark, fontWeight: '800' },
});
