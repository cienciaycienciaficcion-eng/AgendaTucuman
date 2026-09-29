import { Linking, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { ThemedText } from '@/components/themed-text';
import { Colors, MaxContentWidth, Spacing } from '@/constants/theme';
import { useRadioData } from '@/data/use-remote-data';

export default function RadioScreen() {
  const { stream, player, online } = useRadioData();

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.hero}>
          <View style={styles.radioIcon}><ThemedText style={styles.radioIconText}>▶</ThemedText></View>
          <ThemedText type="title">Radio</ThemedText>
          <ThemedText themeColor="textSecondary" style={styles.center}>
            Escuchá la radio de Agenda Tucumán.
          </ThemedText>
        </View>

        <Pressable onPress={() => Linking.openURL(stream)} style={styles.play}>
          <ThemedText style={styles.playText}>▶  Abrir transmisión</ThemedText>
        </Pressable>

        <Pressable onPress={() => Linking.openURL(player)} style={styles.secondary}>
          <ThemedText style={styles.secondaryText}>Abrir reproductor web</ThemedText>
        </Pressable>

        <View style={styles.info}>
          <ThemedText themeColor="textSecondary">
            {online ? 'Fuente de radio actualizada desde GitHub.' : 'Usando la transmisión guardada en la app.'}
          </ThemedText>
          <ThemedText type="subtitle">Transmisión directa</ThemedText>
          <ThemedText themeColor="textSecondary">
            La app utiliza el stream de audio directo de Shock Media, sin depender del reproductor embebido.
          </ThemedText>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles=StyleSheet.create({
  safe:{flex:1,backgroundColor:Colors.light.background},
  content:{width:'100%',maxWidth:MaxContentWidth,alignSelf:'center',padding:Spacing.three,paddingBottom:110},
  hero:{alignItems:'center',paddingVertical:42,gap:10},
  radioIcon:{width:90,height:90,borderRadius:45,backgroundColor:Colors.light.primary,alignItems:'center',justifyContent:'center',marginBottom:8},
  radioIconText:{color:'#fff',fontSize:30,marginLeft:4},
  center:{textAlign:'center'},
  play:{backgroundColor:Colors.light.primary,borderRadius:16,padding:17,alignItems:'center'},
  playText:{color:'#fff',fontWeight:'800',fontSize:16},
  secondary:{marginTop:10,borderWidth:1,borderColor:Colors.light.border,borderRadius:16,padding:15,alignItems:'center',backgroundColor:'#fff'},
  secondaryText:{fontWeight:'700',color:Colors.light.primaryDark},
  info:{marginTop:24,backgroundColor:'#fff',borderWidth:1,borderColor:Colors.light.border,borderRadius:18,padding:18,gap:7},
});
