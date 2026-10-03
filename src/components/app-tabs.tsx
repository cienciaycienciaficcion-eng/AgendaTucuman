import { NativeTabs } from 'expo-router/unstable-native-tabs';
import { Colors } from '@/constants/theme';

export default function AppTabs() {
  const colors = Colors.light;

  return (
    <NativeTabs
      backgroundColor={colors.backgroundElement}
      indicatorColor={colors.backgroundSelected}
      iconColor={{ default: colors.textSecondary, selected: colors.primary }}
      labelStyle={{
        default: { color: colors.textSecondary, fontSize: 11, fontWeight: '600' },
        selected: { color: colors.primary, fontSize: 11, fontWeight: '800' },
      }}
      labelVisibilityMode="labeled"
      disableTransparentOnScrollEdge
    >
      <NativeTabs.Trigger name="index">
        <NativeTabs.Trigger.Icon md={{ default: 'home', selected: 'home' }} sf={{ default: 'house', selected: 'house.fill' }} />
        <NativeTabs.Trigger.Label>Agenda</NativeTabs.Trigger.Label>
      </NativeTabs.Trigger>

      <NativeTabs.Trigger name="cine">
        <NativeTabs.Trigger.Icon md={{ default: 'movie', selected: 'movie' }} sf={{ default: 'film', selected: 'film.fill' }} />
        <NativeTabs.Trigger.Label>Cine</NativeTabs.Trigger.Label>
      </NativeTabs.Trigger>

      <NativeTabs.Trigger name="radio">
        <NativeTabs.Trigger.Icon md={{ default: 'radio', selected: 'radio' }} sf={{ default: 'radio', selected: 'radio.fill' }} />
        <NativeTabs.Trigger.Label>Radio</NativeTabs.Trigger.Label>
      </NativeTabs.Trigger>

      <NativeTabs.Trigger name="proximamente">
        <NativeTabs.Trigger.Icon md={{ default: 'event', selected: 'event' }} sf={{ default: 'calendar.badge.clock', selected: 'calendar.badge.clock' }} />
        <NativeTabs.Trigger.Label>Próximamente</NativeTabs.Trigger.Label>
      </NativeTabs.Trigger>

      <NativeTabs.Trigger name="services">
        <NativeTabs.Trigger.Icon md={{ default: 'build', selected: 'build' }} sf={{ default: 'wrench.and.screwdriver', selected: 'wrench.and.screwdriver.fill' }} />
        <NativeTabs.Trigger.Label>Servicios</NativeTabs.Trigger.Label>
      </NativeTabs.Trigger>
    </NativeTabs>
  );
}
