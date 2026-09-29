import { Linking, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { ThemedText } from '@/components/themed-text';
import { Colors, MaxContentWidth, Spacing } from '@/constants/theme';

const items = [
  { title: 'A dónde comemos', subtitle: 'Restaurantes y lugares para comer en Tucumán', url: 'https://www.google.com/maps/search/restaurantes+Tucum%C3%A1n' },
  { title: 'Agenda Tucumán', subtitle: 'Fuente original de los eventos', url: 'https://agendatucuman.com.ar/' },
  { title: 'Cinemacenter', subtitle: 'Cartelera oficial de Tucumán', url: 'https://www.cinemacenter.com.ar/cartelera#contenido' },
];

export default function MoreScreen() {
  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView contentContainerStyle={styles.content}>
        <ThemedText type="title">Más</ThemedText>
        <ThemedText themeColor="textSecondary" style={styles.subtitle}>Servicios y enlaces de Agenda Tucumán.</ThemedText>

        {items.map(item => (
          <Pressable key={item.title} onPress={() => Linking.openURL(item.url)} style={({pressed}) => [styles.card, pressed && {opacity:.7}]}>
            <View style={styles.icon}><ThemedText style={styles.iconText}>→</ThemedText></View>
            <View style={{flex:1}}>
              <ThemedText type="subtitle">{item.title}</ThemedText>
              <ThemedText themeColor="textSecondary">{item.subtitle}</ThemedText>
            </View>
          </Pressable>
        ))}

        <View style={styles.about}>
          <ThemedText type="subtitle">Agenda Tucumán</ThemedText>
          <ThemedText themeColor="textSecondary">Eventos, cine y radio en un solo lugar.</ThemedText>
          <ThemedText themeColor="textSecondary">Versión 1.1.0</ThemedText>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles=StyleSheet.create({
  safe:{flex:1,backgroundColor:Colors.light.background},
  content:{width:'100%',maxWidth:MaxContentWidth,alignSelf:'center',padding:Spacing.three,paddingBottom:110},
  subtitle:{marginTop:5,marginBottom:20},
  card:{backgroundColor:'#fff',borderWidth:1,borderColor:Colors.light.border,borderRadius:18,padding:16,flexDirection:'row',gap:14,alignItems:'center',marginBottom:10},
  icon:{width:44,height:44,borderRadius:14,backgroundColor:'#E2F4E9',alignItems:'center',justifyContent:'center'},
  iconText:{color:Colors.light.primaryDark,fontSize:24,fontWeight:'800'},
  about:{marginTop:24,backgroundColor:'#fff',borderRadius:18,padding:18,gap:6,borderWidth:1,borderColor:Colors.light.border},
});
