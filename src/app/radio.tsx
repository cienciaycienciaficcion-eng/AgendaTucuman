import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { ThemedText } from '@/components/themed-text';
import { Colors, MaxContentWidth, Spacing } from '@/constants/theme';
import { useRadioPlayer } from '@/context/radio-context';

export default function RadioScreen() {
  const { playing, loading, online, currentTrack, play, pause, stop } = useRadioPlayer();

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.hero}>
          <View style={[styles.radioIcon, playing && styles.radioIconPlaying]}><ThemedText style={styles.radioIconText}>{playing ? '❚❚' : '▶'}</ThemedText></View>
          <ThemedText type="title">Radio</ThemedText>
          <ThemedText themeColor="textSecondary" style={styles.center}>Escuchá Agenda Tucumán directamente desde la app.</ThemedText>
        </View>

        <Pressable onPress={playing ? pause : play} style={styles.play}>
          <ThemedText style={styles.playText}>{playing ? '❚❚  Pausar radio' : '▶  Escuchar radio'}</ThemedText>
        </Pressable>

        {playing && <Pressable onPress={stop} style={styles.secondary}>
          <ThemedText style={styles.secondaryText}>■  Detener</ThemedText>
        </Pressable>}

        <View style={styles.status}>
          <View style={[styles.dot, online && styles.dotOnline]} />
          <ThemedText themeColor="textSecondary">{loading ? 'Conectando con la radio…' : online ? 'Radio en vivo' : 'Fuente configurada'}</ThemedText>
        </View>

        <View style={styles.nowPlaying}>
          <ThemedText type="smallBold" themeColor="textSecondary">SONANDO AHORA</ThemedText>
          <ThemedText type="subtitle" style={styles.trackTitle} numberOfLines={2}>
            {currentTrack?.title || 'Esperando metadata de la radio…'}
          </ThemedText>
          {currentTrack?.artist ? (
            <ThemedText themeColor="textSecondary" style={styles.trackArtist} numberOfLines={1}>
              {currentTrack.artist}
            </ThemedText>
          ) : null}
        </View>

      </ScrollView>
    </SafeAreaView>
  );
}

const styles=StyleSheet.create({
  safe:{flex:1,backgroundColor:Colors.light.background}, content:{width:'100%',maxWidth:MaxContentWidth,alignSelf:'center',paddingHorizontal:Spacing.three,paddingTop:12,paddingBottom:130}, hero:{alignItems:'center',paddingVertical:42,gap:10}, radioIcon:{width:90,height:90,borderRadius:45,backgroundColor:Colors.light.primary,alignItems:'center',justifyContent:'center',marginBottom:8}, radioIconPlaying:{backgroundColor:Colors.light.primaryDark}, radioIconText:{color:'#fff',fontSize:30,marginLeft:4}, center:{textAlign:'center'}, play:{backgroundColor:Colors.light.primary,borderRadius:16,padding:17,alignItems:'center'}, playText:{color:'#fff',fontWeight:'800',fontSize:16}, secondary:{marginTop:10,borderWidth:1,borderColor:Colors.light.border,borderRadius:16,padding:15,alignItems:'center',backgroundColor:Colors.light.backgroundElement}, secondaryText:{fontWeight:'700',color:Colors.light.primaryDark}, status:{flexDirection:'row',alignItems:'center',justifyContent:'center',gap:8,marginTop:18}, nowPlaying:{marginTop:24,backgroundColor:'#fff',borderWidth:1,borderColor:Colors.light.border,borderRadius:18,padding:18}, trackTitle:{fontSize:24,lineHeight:30,marginTop:5}, trackArtist:{fontSize:16,marginTop:2}, dot:{width:8,height:8,borderRadius:4,backgroundColor:Colors.light.textSecondary}, dotOnline:{backgroundColor:Colors.light.primary},
});
