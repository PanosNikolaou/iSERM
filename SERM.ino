#include <OneWire.h>
#include <DallasTemperature.h>
#include <SoftwareSerial.h>

#define uint  unsigned int
#define ulong unsigned long

#define PIN_ANEMOMETER  2     // Digital 2
#define PIN_VANE        5     // Analog 5

// How often we want to calculate wind speed or direction
#define MSECS_CALC_WIND_SPEED 1000 //5000 initial
#define MSECS_CALC_WIND_DIR   1000

volatile int numRevsAnemometer = 0; // Incremented in the interrupt
ulong nextCalcSpeed;                // When we next calc the wind speed
ulong nextCalcDir;                  // When we next calc the direction
ulong time;                         // Millis() at each start of loop().

// ADC readings:
#define NUMDIRS 8
ulong   adc[NUMDIRS] = {26, 45, 77, 118, 161, 196, 220, 256};

// These directions match 1-for-1 with the values in adc, but
// will have to be adjusted as noted above. Modify 'dirOffset'
// to which direction is 'away' (it's West here).
char *strVals[NUMDIRS] = {"W","NW","N","SW","NE","S","SE","E"};
byte dirOffset=0;

// Data wire is plugged into pin 2 on the Arduino
#define ONE_WIRE_BUS 5

// XBee's DOUT (TX) is connected to pin 2 (Arduino's Software RX)
// XBee's DIN (RX) is connected to pin 3 (Arduino's Software TX)
SoftwareSerial XBee(2, 3); // RX, TX 
int humPin = 3;
// Setup a oneWire instance to communicate with any OneWire devices 
// (not just Maxim/Dallas temperature ICs)
OneWire oneWire(ONE_WIRE_BUS);

// Pass our oneWire reference to Dallas Temperature.
DallasTemperature sensors(&oneWire);
 
/************************Hardware Related Macros************************************/
#define         MQ_PIN                       (0)     //define which analog input channel you are going to use
#define         RL_VALUE                     (5)     //define the load resistance on the board, in kilo ohms
#define         RO_CLEAN_AIR_FACTOR          (9.83)  //RO_CLEAR_AIR_FACTOR=(Sensor resistance in clean air)/RO,
                                                     //which is derived from the chart in datasheet
 
/***********************Software Related Macros************************************/
#define         CALIBARAION_SAMPLE_TIMES     (20)    //define how many samples you are going to take in the calibration phase
#define         CALIBRATION_SAMPLE_INTERVAL  (500)   //define the time interal(in milisecond) between each samples in the
                                                     //cablibration phase
#define         READ_SAMPLE_INTERVAL         (50)    //define how many samples you are going to take in normal operation
#define         READ_SAMPLE_TIMES            (5)     //define the time interal(in milisecond) between each samples in 
                                                     //normal operation
 
/**********************Application Related Macros**********************************/
#define         GAS_LPG                      (0)
#define         GAS_CO                       (1)
#define         GAS_SMOKE                    (2)
 
/*****************************Globals***********************************************/
float           LPGCurve[3]  =  {2.3,0.21,-0.47};   //two points are taken from the curve. 
                                                    //with these two points, a line is formed which is "approximately equivalent"
                                                    //to the original curve. 
                                                    //data format:{ x, y, slope}; point1: (lg200, 0.21), point2: (lg10000, -0.59) 
float           COCurve[3]  =  {2.3,0.72,-0.34};    //two points are taken from the curve. 
                                                    //with these two points, a line is formed which is "approximately equivalent" 
                                                    //to the original curve.
                                                    //data format:{ x, y, slope}; point1: (lg200, 0.72), point2: (lg10000,  0.15) 
float           SmokeCurve[3] ={2.3,0.53,-0.44};    //two points are taken from the curve. 
                                                    //with these two points, a line is formed which is "approximately equivalent" 
                                                    //to the original curve.
                                                    //data format:{ x, y, slope}; point1: (lg200, 0.53), point2: (lg10000,  -0.22)                                                     
float           Ro           =  10;                 //Ro is initialized to 10 kilo ohms

void setup()   /*----( SETUP: RUNS ONCE )----*/
{

  // initialise the serial output
  Serial.begin(9600);
  
  Serial.println("Operation started");
  Serial.print("Calibrating Sensors...\n");                
  
  Ro = MQCalibration(MQ_PIN);                       //Calibrating the sensor. Please make sure the sensor is in clean air 
                                                    //when you perform the calibration                    
  Serial.print("Calibration is done...\n"); 
  Serial.print("Ro=");
  Serial.print(Ro);
  Serial.print("kohm");
  Serial.print("\n");

  XBee.begin(9600);

    // Start up the library
  sensors.begin();
  
  pinMode(PIN_ANEMOMETER, INPUT);
  digitalWrite(PIN_ANEMOMETER, HIGH);
  attachInterrupt(0, countAnemometer, FALLING);
  nextCalcSpeed = millis() + MSECS_CALC_WIND_SPEED;
  nextCalcDir   = millis() + MSECS_CALC_WIND_DIR;

}/*--(end setup )---*/

void loop()   /*----( LOOP: RUNS CONSTANTLY )----*/
{
   
   sensors.requestTemperatures(); // Send the command to get temperatures

    double temperatureC = sensors.getTempCByIndex(0);
  
    // read the value from the pin
    int humReading = analogRead(humPin); 
    // convert it into voltage (Vcc = 5V)
    double volt = humReading / 1023.0 * 5;
    // calculate the sensor humitidy
    double sensorRH = 161.*volt/5 - 25.8;
    // adapt this for the given temperature
    double trueRH = (sensorRH / (1.0546 - 0.0026*temperatureC));  

    // print it to the serial output
    Serial.print("Humidity : ");
    Serial.print(trueRH);
    Serial.print(" ");
    Serial.print("Temperature : ");
    Serial.print(temperatureC);
    Serial.print(" ");
    Serial.print("LPG:"); 
    Serial.print(MQGetGasPercentage(MQRead(MQ_PIN)/Ro,GAS_LPG) );
    Serial.print( "ppm" );
    Serial.print(" ");   
    Serial.print("CO:"); 
    Serial.print(MQGetGasPercentage(MQRead(MQ_PIN)/Ro,GAS_CO));
    Serial.print( "ppm" );
    Serial.print(" ");   
    Serial.print("SMOKE:");
    Serial.print(MQGetGasPercentage(MQRead(MQ_PIN)/Ro,GAS_SMOKE));
    Serial.print( "ppm" );
    Serial.print(" ");

    float rcvSmoke = MQGetGasPercentage(MQRead(MQ_PIN)/Ro,GAS_SMOKE);
    String SMOKE= FloatToString( rcvSmoke , 1);
    char Buf[10];
    SMOKE.toCharArray(Buf,10);

    float rcvCo = MQGetGasPercentage(MQRead(MQ_PIN)/Ro,GAS_CO);
    String GAS= FloatToString( rcvCo , 1);
    char Buf0[10];
    GAS.toCharArray(Buf0,10);
    
    float rcvLpg = MQGetGasPercentage(MQRead(MQ_PIN)/Ro,GAS_LPG);
    String LPG= FloatToString( rcvLpg , 1);
    char Buf1[10];
    LPG.toCharArray(Buf1,10);

    float trcHumidity = trueRH;
    String HUMIDITY = FloatToString( trcHumidity , 1);
    char Buf2[10];
    HUMIDITY.toCharArray(Buf2,10);
    
    float trcTemperature = temperatureC;
    String TEMPERATURE = FloatToString( trcTemperature , 1);
    char Buf3[10];
    TEMPERATURE.toCharArray(Buf3,10);
    
    float wspeed = 2.23693629 * calcWindSpeed();
    String WINDSPEED = FloatToString( wspeed , 1);
    char Buf4[10];
    WINDSPEED.toCharArray(Buf4,10);
    
    String WINDDIR = calcWindDir();
    char Buf5[5];
    WINDDIR.toCharArray(Buf5,5);
    
    String command = "'{\"smk\":" + SMOKE + ",\"lpg\":" + LPG  + ",\"co\":" + GAS  +",\"hum\":" + HUMIDITY + ",\"temp\":"+ TEMPERATURE + ",\"wndspd\":" + WINDSPEED + ",\"wnddir\":" + "\"" + WINDDIR + "\"" +  "}'";
    char strbuf[100];
    command.toCharArray(strbuf,100);
    XBee.write(strbuf);
    XBee.write("\n");
    
    Serial.print("\n");   
}

void countAnemometer() {
   numRevsAnemometer++;
}

String calcWindDir() {
   int val;
   byte x, reading;

   val = analogRead(PIN_VANE);
   val >>=2;                        // Shift to 255 range
   reading = val;

   // Look the reading up in directions table. Find the first value
   // that's >= to what we got.
   for (x=0; x<NUMDIRS; x++) {
      if (adc[x] >= reading)
         break;
   }
   
   x = (x + dirOffset) % 8;   // Adjust for orientation
   Serial.print(" Wind Direction: ");
   Serial.print(strVals[x]);
   Serial.print("\n");
   return strVals[x];
}

float calcWindSpeed() {
   int x,iSpeed;
   int SpDec,SpInt;
   // This will produce mph * 10
   // (didn't calc right when done as one statement)
   long speed = 14920;
   speed *= numRevsAnemometer;

   speed /= MSECS_CALC_WIND_SPEED;
   iSpeed = speed;         // Need this for formatting below

   Serial.print("Wind speed: ");
   x = iSpeed / 10;
   SpDec = x;
   Serial.print(x);
   Serial.print('.');
   x = iSpeed % 10;
   SpInt = x;
   Serial.print(x);
   numRevsAnemometer = 0;        // Reset counter
   return ((float)SpInt+(SpDec/10.)) ; // epestrepse real
}

/****************** MQResistanceCalculation ****************************************
Input:   raw_adc - raw value read from adc, which represents the voltage
Output:  the calculated sensor resistance
Remarks: The sensor and the load resistor forms a voltage divider. Given the voltage
         across the load resistor and its resistance, the resistance of the sensor
         could be derived.
************************************************************************************/ 
float MQResistanceCalculation(int raw_adc)
{
  return ( ((float)RL_VALUE*(1023-raw_adc)/raw_adc));
}
 
/***************************** MQCalibration ****************************************
Input:   mq_pin - analog channel
Output:  Ro of the sensor
Remarks: This function assumes that the sensor is in clean air. It use  
         MQResistanceCalculation to calculates the sensor resistance in clean air 
         and then divides it with RO_CLEAN_AIR_FACTOR. RO_CLEAN_AIR_FACTOR is about 
         10, which differs slightly between different sensors.
************************************************************************************/ 
float MQCalibration(int mq_pin)
{
  int i;
  float val=0;
 
  for (i=0;i<CALIBARAION_SAMPLE_TIMES;i++) {            //take multiple samples
    val += MQResistanceCalculation(analogRead(mq_pin));
    delay(CALIBRATION_SAMPLE_INTERVAL);
  }
  val = val/CALIBARAION_SAMPLE_TIMES;                   //calculate the average value
 
  val = val/RO_CLEAN_AIR_FACTOR;                        //divided by RO_CLEAN_AIR_FACTOR yields the Ro 
                                                        //according to the chart in the datasheet 
 
  return val; 
}
/*****************************  MQRead *********************************************
Input:   mq_pin - analog channel
Output:  Rs of the sensor
Remarks: This function use MQResistanceCalculation to caculate the sensor resistenc (Rs).
         The Rs changes as the sensor is in the different consentration of the target
         gas. The sample times and the time interval between samples could be configured
         by changing the definition of the macros.
************************************************************************************/ 
float MQRead(int mq_pin)
{
  int i;
  float rs=0;
 
  for (i=0;i<READ_SAMPLE_TIMES;i++) {
    rs += MQResistanceCalculation(analogRead(mq_pin));
    delay(READ_SAMPLE_INTERVAL);
  }
 
  rs = rs/READ_SAMPLE_TIMES;
 
  return rs;  
}
 
/*****************************  MQGetGasPercentage **********************************
Input:   rs_ro_ratio - Rs divided by Ro
         gas_id      - target gas type
Output:  ppm of the target gas
Remarks: This function passes different curves to the MQGetPercentage function which 
         calculates the ppm (parts per million) of the target gas.
************************************************************************************/ 
int MQGetGasPercentage(float rs_ro_ratio, int gas_id)
{
  if ( gas_id == GAS_LPG ) {
     return MQGetPercentage(rs_ro_ratio,LPGCurve);
  } else if ( gas_id == GAS_CO ) {
     return MQGetPercentage(rs_ro_ratio,COCurve);
  } else if ( gas_id == GAS_SMOKE ) {
     return MQGetPercentage(rs_ro_ratio,SmokeCurve);
  }    
 
  return 0;
}
 
/*****************************  MQGetPercentage **********************************
Input:   rs_ro_ratio - Rs divided by Ro
         pcurve      - pointer to the curve of the target gas
Output:  ppm of the target gas
Remarks: By using the slope and a point of the line. The x(logarithmic value of ppm) 
         of the line could be derived if y(rs_ro_ratio) is provided. As it is a 
         logarithmic coordinate, power of 10 is used to convert the result to non-logarithmic 
         value.
************************************************************************************/ 
int  MQGetPercentage(float rs_ro_ratio, float *pcurve)
{
  return (pow(10,( ((log(rs_ro_ratio)-pcurve[1])/pcurve[2]) + pcurve[0])));
}

    // F L O A T  To  S T R I N G   Conversion
  
  String FloatToString(float flt, int presisionNum ){
   unsigned int TempInt= flt;   // get the integer part of float
    float TempFlt= flt-TempInt; // get the demical part of float
   unsigned int TempDec=  TempFlt*(pow(10,presisionNum)); //get demical in presision
   // int TempDec= TempFlt*100; //get demical in presision
    String FtoStrTemp="";
      FtoStrTemp=  TempInt;
      FtoStrTemp+= ".";
    if(TempDec<10){ //if only one dec 
     // FtoStrTemp+= "0";
        for(int i=0;i<(presisionNum-1);i++){ FtoStrTemp+= "0";}
       }//if
      FtoStrTemp+= TempDec;
    return FtoStrTemp;  
  }//Float to String 

