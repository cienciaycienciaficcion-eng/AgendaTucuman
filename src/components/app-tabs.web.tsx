import {
  Tabs,
  TabList,
  TabTrigger,
  TabSlot,
  TabTriggerSlotProps,
  TabListProps,
} from 'expo-router/ui';
import { Pressable, useColorScheme, View, StyleSheet, Text } from 'react-native';

import { Colors, MaxContentWidth } from '@/constants/theme';

const tabs = [
  { name: 'index', href: '/', label: 'Agenda', icon: '▣' },
  { name: 'calendar', href: '/calendar', label: 'Calendario', icon: '□' },
  { name: 'cine', href: '/cine', label: 'Cine', icon: '▶' },
  { name: 'radio', href: '/radio', label: 'Radio', icon: '◉' },
  { name: 'services', href: '/services', label: 'Servicios', icon: '⚙' },
] as const;

export default function AppTabs() {
  return (
    <Tabs>
      <TabSlot style={styles.slot} />

      <TabList asChild>
        <CustomTabList>
          {tabs.map((tab) => (
            <TabTrigger key={tab.name} name={tab.name} href={tab.href} asChild>
              <TabButton icon={tab.icon}>{tab.label}</TabButton>
            </TabTrigger>
          ))}
        </CustomTabList>
      </TabList>
    </Tabs>
  );
}

export function TabButton({
  children,
  icon,
  isFocused,
  ...props
}: TabTriggerSlotProps & { icon: string }) {
  return (
    <Pressable
      {...props}
      style={({ pressed }) => [styles.tabButton, pressed && styles.pressed]}
    >
      <View style={[styles.tabContent, isFocused && styles.tabContentActive]}>
        <Text style={[styles.icon, isFocused && styles.iconActive]}>
          {icon}
        </Text>
        <Text style={[styles.label, isFocused && styles.labelActive]}>
          {children}
        </Text>
      </View>
    </Pressable>
  );
}

export function CustomTabList(props: TabListProps) {
  const scheme = useColorScheme();
  const colors = Colors[scheme === 'dark' ? 'dark' : 'light'];

  return (
    <View {...props} style={styles.container}>
      <View
        style={[
          styles.bar,
          {
            backgroundColor: colors.backgroundElement,
            borderColor: colors.border,
          },
        ]}
      >
        {props.children}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  slot: {
    flex: 1,
  },

  container: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    zIndex: 1000,
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingTop: 8,
    paddingBottom: 12,
  },

  bar: {
    width: '100%',
    maxWidth: MaxContentWidth,
    height: 70,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-around',
    borderWidth: 1,
    borderRadius: 22,
    paddingHorizontal: 6,
    shadowColor: '#000',
    shadowOpacity: 0.12,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 8,
  },

  tabButton: {
    flex: 1,
    height: 58,
    marginHorizontal: 3,
    borderRadius: 16,
  },

  tabContent: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 16,
  },

  tabContentActive: {
    backgroundColor: '#E2F4E9',
  },

  icon: {
    fontSize: 18,
    lineHeight: 21,
    color: Colors.light.textSecondary,
    marginBottom: 2,
    fontWeight: '700',
  },

  iconActive: {
    color: Colors.light.primary,
  },

  label: {
    fontSize: 11,
    color: Colors.light.textSecondary,
    fontWeight: '600',
  },

  labelActive: {
    color: Colors.light.primaryDark,
    fontWeight: '800',
  },

  pressed: {
    opacity: 0.65,
  },
});
