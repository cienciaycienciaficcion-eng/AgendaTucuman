import { Image } from 'expo-image';
import * as SplashScreen from 'expo-splash-screen';
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated, { Easing, Keyframe } from 'react-native-reanimated';
import { scheduleOnRN } from 'react-native-worklets';

const DURATION = 600;

export function AnimatedSplashOverlay() {
  const [animate, setAnimate] = useState(false);
  const [visible, setVisible] = useState(true);

  if (!visible) return null;

  const splashKeyframe = new Keyframe({
    0: { opacity: 1, transform: [{ scale: 1 }] },
    70: { opacity: 0.2, transform: [{ scale: 1.02 }], easing: Easing.out(Easing.ease) },
    100: { opacity: 0, transform: [{ scale: 1.04 }], easing: Easing.out(Easing.ease) },
  });

  const image = <Image style={styles.logo} contentFit="contain" source={require('@/assets/images/agenda-logo.png')} />;

  return animate ? (
    <Animated.View
      entering={splashKeyframe.duration(DURATION).withCallback((finished) => {
        'worklet';
        if (finished) scheduleOnRN(setVisible, false);
      })}
      style={styles.splashOverlay}
    >
      {image}
    </Animated.View>
  ) : (
    <View
      onLayout={() => {
        SplashScreen.hideAsync().finally(() => setAnimate(true));
      }}
      style={styles.splashOverlay}
    >
      {image}
    </View>
  );
}

export function AnimatedIcon() {
  return (
    <View style={styles.iconContainer}>
      <Image style={styles.logo} contentFit="contain" source={require('@/assets/images/agenda-logo.png')} />
    </View>
  );
}

const styles = StyleSheet.create({
  iconContainer: { justifyContent: 'center', alignItems: 'center', width: 300, height: 120 },
  logo: { width: 300, height: 100 },
  splashOverlay: {
    ...StyleSheet.absoluteFill,
    backgroundColor: '#FFFFFF',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1000,
  },
});
