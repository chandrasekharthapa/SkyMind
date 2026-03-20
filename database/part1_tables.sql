-- ============================================================
-- SkyMind PART 1 — Tables, Data, RLS
-- Run this first. Then run part2_triggers.sql
-- ============================================================

-- ── DROP EVERYTHING ──────────────────────────────────────────
DROP VIEW  IF EXISTS public.v_booking_details      CASCADE;
DROP VIEW  IF EXISTS public.v_pending_notifications CASCADE;
DROP VIEW  IF EXISTS public.v_active_alerts        CASCADE;
DROP VIEW  IF EXISTS public.v_domestic_routes      CASCADE;
DROP TABLE IF EXISTS public.otp_verifications      CASCADE;
DROP TABLE IF EXISTS public.notifications          CASCADE;
DROP TABLE IF EXISTS public.notification_templates CASCADE;
DROP TABLE IF EXISTS public.passengers             CASCADE;
DROP TABLE IF EXISTS public.bookings               CASCADE;
DROP TABLE IF EXISTS public.price_alerts           CASCADE;
DROP TABLE IF EXISTS public.saved_searches         CASCADE;
DROP TABLE IF EXISTS public.price_history          CASCADE;
DROP TABLE IF EXISTS public.flights                CASCADE;
DROP TABLE IF EXISTS public.coupons                CASCADE;
DROP TABLE IF EXISTS public.user_sessions          CASCADE;
DROP TABLE IF EXISTS public.profiles               CASCADE;
DROP TABLE IF EXISTS public.routes                 CASCADE;
DROP TABLE IF EXISTS public.airlines               CASCADE;
DROP TABLE IF EXISTS public.airports               CASCADE;
DROP FUNCTION IF EXISTS public.handle_new_user()           CASCADE;
DROP FUNCTION IF EXISTS public.update_updated_at()         CASCADE;
DROP FUNCTION IF EXISTS public.handle_booking_confirmed()  CASCADE;

-- ── EXTENSIONS ────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ============================================================
-- AIRPORTS
-- ============================================================
CREATE TABLE public.airports (
  iata_code        TEXT PRIMARY KEY,
  icao_code        TEXT,
  name             TEXT NOT NULL,
  city             TEXT NOT NULL,
  state            TEXT,
  region           TEXT,
  country          TEXT NOT NULL DEFAULT 'India',
  country_code     TEXT NOT NULL DEFAULT 'IN',
  latitude         DECIMAL(9,6),
  longitude        DECIMAL(9,6),
  timezone         TEXT DEFAULT 'Asia/Kolkata',
  elevation_ft     INT,
  is_domestic      BOOLEAN DEFAULT TRUE,
  is_international BOOLEAN DEFAULT FALSE,
  is_active        BOOLEAN DEFAULT TRUE,
  terminal_count   INT DEFAULT 1,
  runway_count     INT DEFAULT 1,
  longest_runway_m INT,
  aai_category     TEXT,
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO public.airports
(iata_code,icao_code,name,city,state,region,country,country_code,
 latitude,longitude,timezone,elevation_ft,is_domestic,is_international,
 is_active,terminal_count,runway_count,longest_runway_m,aai_category)
VALUES
-- ── NORTH ─────────────────────────────────────────────────────
('DEL','VIDP','Indira Gandhi International Airport','New Delhi','Delhi','NORTH','India','IN',28.5665,77.1031,'Asia/Kolkata',777,true,true,true,3,3,4430,'A'),
('ATQ','VIAR','Sri Guru Ram Dass Jee International Airport','Amritsar','Punjab','NORTH','India','IN',31.7096,74.7973,'Asia/Kolkata',756,true,true,true,1,1,3200,'B'),
('IXC','VICG','Chandigarh International Airport','Chandigarh','Chandigarh','NORTH','India','IN',30.6735,76.7885,'Asia/Kolkata',1012,true,false,true,1,1,2740,'B'),
('LUH','VILD','Ludhiana Airport','Ludhiana','Punjab','NORTH','India','IN',30.8547,75.9526,'Asia/Kolkata',834,true,false,true,1,1,1800,'D'),
('BUP','VIBT','Bathinda Airport','Bathinda','Punjab','NORTH','India','IN',30.2701,74.7557,'Asia/Kolkata',663,true,false,true,1,1,2750,'D'),
('IXJ','VIJU','Jammu Airport','Jammu','J&K','NORTH','India','IN',32.6891,74.8374,'Asia/Kolkata',1029,true,false,true,1,1,2895,'B'),
('SXR','VISR','Sheikh ul-Alam International Airport','Srinagar','J&K','NORTH','India','IN',33.9871,74.7742,'Asia/Kolkata',5429,true,false,true,1,1,3050,'B'),
('IXL','VILH','Kushok Bakula Rimpochhe Airport','Leh','Ladakh','NORTH','India','IN',34.1359,77.5465,'Asia/Kolkata',10682,true,false,true,1,1,3354,'C'),
('KTU','VIKA','Kargil Airport','Kargil','Ladakh','NORTH','India','IN',34.5687,76.1540,'Asia/Kolkata',8790,true,false,true,1,1,1300,'E'),
('DED','VIDN','Jolly Grant Airport','Dehradun','Uttarakhand','NORTH','India','IN',30.1897,78.1803,'Asia/Kolkata',1796,true,false,true,1,1,2398,'C'),
('PGH','VIPC','Pantnagar Airport','Pantnagar','Uttarakhand','NORTH','India','IN',29.0334,79.4737,'Asia/Kolkata',799,true,false,true,1,1,1500,'D'),
('DHM','VIDD','Kangra Gaggal Airport','Dharamshala','Himachal Pradesh','NORTH','India','IN',32.1651,76.2634,'Asia/Kolkata',2525,true,false,true,1,1,1372,'D'),
('KUU','VIKU','Bhuntar Airport','Kullu','Himachal Pradesh','NORTH','India','IN',31.8767,77.1544,'Asia/Kolkata',3038,true,false,true,1,1,1150,'E'),
('SLV','VISL','Shimla Airport','Shimla','Himachal Pradesh','NORTH','India','IN',31.0818,77.0680,'Asia/Kolkata',5072,true,false,true,1,1,1180,'E'),
('LKO','VILK','Chaudhary Charan Singh International Airport','Lucknow','Uttar Pradesh','NORTH','India','IN',26.7606,80.8893,'Asia/Kolkata',410,true,true,true,1,2,2743,'A'),
('VNS','VIBN','Lal Bahadur Shastri International Airport','Varanasi','Uttar Pradesh','NORTH','India','IN',25.4524,82.8593,'Asia/Kolkata',266,true,false,true,1,1,2743,'B'),
('AGR','VIAG','Agra Airport','Agra','Uttar Pradesh','NORTH','India','IN',27.1558,77.9609,'Asia/Kolkata',551,true,false,true,1,1,2745,'C'),
('IXD','VIAL','Bamrauli Airport','Prayagraj','Uttar Pradesh','NORTH','India','IN',25.4401,81.7339,'Asia/Kolkata',322,true,false,true,1,1,2743,'C'),
('KNU','VIKG','Chakeri Airport','Kanpur','Uttar Pradesh','NORTH','India','IN',26.4044,80.3649,'Asia/Kolkata',410,true,false,true,1,1,2745,'D'),
('GOP','VEGP','Gorakhpur Airport','Gorakhpur','Uttar Pradesh','NORTH','India','IN',26.7397,83.4497,'Asia/Kolkata',259,true,false,true,1,1,2744,'C'),
('JAI','VIJP','Jaipur International Airport','Jaipur','Rajasthan','NORTH','India','IN',26.8242,75.8122,'Asia/Kolkata',1263,true,true,true,2,2,3405,'A'),
('JDH','VEJD','Jodhpur Airport','Jodhpur','Rajasthan','NORTH','India','IN',26.2511,73.0489,'Asia/Kolkata',717,true,false,true,1,1,3048,'B'),
('UDR','VAUD','Maharana Pratap Airport','Udaipur','Rajasthan','NORTH','India','IN',24.6177,73.8961,'Asia/Kolkata',1684,true,false,true,1,1,2286,'C'),
('JSA','VIJS','Jaisalmer Airport','Jaisalmer','Rajasthan','NORTH','India','IN',26.8887,70.8650,'Asia/Kolkata',751,true,false,true,1,1,3048,'D'),
('KQH','VIKG','Kishangarh Airport','Ajmer','Rajasthan','NORTH','India','IN',26.5901,74.8139,'Asia/Kolkata',1500,true,false,true,1,1,3600,'C'),
('BKB','VIBK','Nal Airport','Bikaner','Rajasthan','NORTH','India','IN',28.0706,73.2072,'Asia/Kolkata',750,true,false,true,1,1,2743,'D'),
('GBD','VIGR','Gwalior Airport','Gwalior','Madhya Pradesh','CENTRAL','India','IN',26.2933,78.2278,'Asia/Kolkata',617,true,false,true,1,1,2745,'C'),
-- ── WEST ───────────────────────────────────────────────────────
('BOM','VABB','Chhatrapati Shivaji Maharaj International Airport','Mumbai','Maharashtra','WEST','India','IN',19.0896,72.8656,'Asia/Kolkata',37,true,true,true,2,2,3660,'A'),
('PNQ','VAPO','Pune Airport','Pune','Maharashtra','WEST','India','IN',18.5821,73.9197,'Asia/Kolkata',1942,true,false,true,1,1,2743,'B'),
('NAG','VANP','Dr. Babasaheb Ambedkar International Airport','Nagpur','Maharashtra','WEST','India','IN',21.0922,79.0473,'Asia/Kolkata',1033,true,true,true,1,1,3200,'B'),
('GOI','VAGO','Goa International Airport','South Goa','Goa','WEST','India','IN',15.3808,73.8314,'Asia/Kolkata',150,true,true,true,1,1,3328,'B'),
('MYA','VOMY','Mopa International Airport','North Goa','Goa','WEST','India','IN',15.7127,73.8651,'Asia/Kolkata',200,true,true,true,1,1,4000,'B'),
('KLH','VAKP','Kolhapur Airport','Kolhapur','Maharashtra','WEST','India','IN',16.6647,74.2894,'Asia/Kolkata',1981,true,false,true,1,1,1800,'D'),
('ISK','VAAU','Nashik-Ozar Airport','Nashik','Maharashtra','WEST','India','IN',20.1192,73.9128,'Asia/Kolkata',1959,true,false,true,1,1,3048,'C'),
('SSE','VASO','Solapur Airport','Solapur','Maharashtra','WEST','India','IN',17.6280,75.9348,'Asia/Kolkata',1584,true,false,true,1,1,1800,'D'),
('SAG','VAND','Shirdi Airport','Shirdi','Maharashtra','WEST','India','IN',19.6888,74.3790,'Asia/Kolkata',1984,true,false,true,1,1,3600,'C'),
('NDC','VANU','Nanded Airport','Nanded','Maharashtra','WEST','India','IN',19.1833,77.3167,'Asia/Kolkata',1250,true,false,true,1,1,2100,'D'),
('QJV','VAAB','Aurangabad Airport','Aurangabad','Maharashtra','WEST','India','IN',19.8627,75.3981,'Asia/Kolkata',1912,true,false,true,1,1,2953,'C'),
('AMD','VAAH','Sardar Vallabhbhai Patel International Airport','Ahmedabad','Gujarat','WEST','India','IN',23.0772,72.6347,'Asia/Kolkata',189,true,true,true,2,2,3200,'A'),
('BDQ','VABO','Vadodara Airport','Vadodara','Gujarat','WEST','India','IN',22.3362,73.2263,'Asia/Kolkata',129,true,false,true,1,1,2745,'B'),
('STV','VASU','Surat Airport','Surat','Gujarat','WEST','India','IN',21.1141,72.7418,'Asia/Kolkata',16,true,false,true,1,1,2905,'B'),
('RAJ','VARK','Rajkot Airport','Rajkot','Gujarat','WEST','India','IN',22.3092,70.7796,'Asia/Kolkata',441,true,false,true,1,1,2750,'C'),
('JGA','VAJI','Jamnagar Airport','Jamnagar','Gujarat','WEST','India','IN',22.4655,70.0126,'Asia/Kolkata',69,true,false,true,1,1,2743,'C'),
('BHJ','VABJ','Bhuj Airport','Bhuj','Gujarat','WEST','India','IN',23.2878,69.6701,'Asia/Kolkata',268,true,false,true,1,1,3500,'C'),
('DIU','VADU','Diu Airport','Diu','Dadra & NH','WEST','India','IN',20.7131,70.9210,'Asia/Kolkata',31,true,false,true,1,1,1400,'D'),
('BKD','VAPR','Porbandar Airport','Porbandar','Gujarat','WEST','India','IN',21.6487,69.6572,'Asia/Kolkata',23,true,false,true,1,1,1981,'D'),
-- ── CENTRAL ────────────────────────────────────────────────────
('BHO','VABP','Raja Bhoj Airport','Bhopal','Madhya Pradesh','CENTRAL','India','IN',23.2875,77.3374,'Asia/Kolkata',1711,true,false,true,1,1,2750,'B'),
('IDR','VAID','Devi Ahilyabai Holkar Airport','Indore','Madhya Pradesh','CENTRAL','India','IN',22.7218,75.8011,'Asia/Kolkata',1850,true,false,true,1,1,2750,'B'),
('JLR','VAJB','Jabalpur Airport','Jabalpur','Madhya Pradesh','CENTRAL','India','IN',23.1778,80.0520,'Asia/Kolkata',1624,true,false,true,1,1,2438,'C'),
('KHI','VAKJ','Khajuraho Airport','Khajuraho','Madhya Pradesh','CENTRAL','India','IN',24.8172,79.9186,'Asia/Kolkata',728,true,false,true,1,1,1981,'D'),
('RPR','VARP','Swami Vivekananda Airport','Raipur','Chhattisgarh','CENTRAL','India','IN',21.1804,81.7388,'Asia/Kolkata',1041,true,false,true,1,1,2743,'B'),
('JRG','VEJH','Jharsuguda Airport','Jharsuguda','Odisha','CENTRAL','India','IN',21.9135,84.0504,'Asia/Kolkata',751,true,false,true,1,1,2285,'C'),
('JAG','VAJG','Jagdalpur Airport','Jagdalpur','Chhattisgarh','CENTRAL','India','IN',19.0742,82.0319,'Asia/Kolkata',1862,true,false,true,1,1,1981,'E'),
-- ── EAST ────────────────────────────────────────────────────────
('CCU','VECC','Netaji Subhas Chandra Bose International Airport','Kolkata','West Bengal','EAST','India','IN',22.6520,88.4463,'Asia/Kolkata',19,true,true,true,2,2,3627,'A'),
('IXB','VEBD','Bagdogra Airport','Siliguri','West Bengal','EAST','India','IN',26.6812,88.3286,'Asia/Kolkata',412,true,false,true,1,1,3050,'B'),
('BBI','VEBS','Biju Patnaik International Airport','Bhubaneswar','Odisha','EAST','India','IN',20.2444,85.8178,'Asia/Kolkata',148,true,true,true,1,1,2743,'B'),
('IXR','VERC','Birsa Munda Airport','Ranchi','Jharkhand','EAST','India','IN',23.3143,85.3217,'Asia/Kolkata',2148,true,false,true,1,1,2397,'B'),
('PAT','VEPT','Jay Prakash Narayan International Airport','Patna','Bihar','EAST','India','IN',25.5913,85.0880,'Asia/Kolkata',170,true,false,true,1,1,2130,'B'),
('GAY','VEGY','Gaya Airport','Gaya','Bihar','EAST','India','IN',24.7444,84.9512,'Asia/Kolkata',380,true,false,true,1,1,2286,'C'),
('DBR','VEDB','Deoghar Airport','Deoghar','Jharkhand','EAST','India','IN',24.4622,86.7086,'Asia/Kolkata',830,true,false,true,1,1,3600,'D'),
('MZU','VEMZ','Muzaffarpur Airport','Muzaffarpur','Bihar','EAST','India','IN',26.1191,85.3133,'Asia/Kolkata',182,true,false,true,1,1,1524,'E'),
('PKR','VEPG','Pakyong Airport','Gangtok','Sikkim','EAST','India','IN',27.2257,88.5849,'Asia/Kolkata',4593,true,false,true,1,1,1750,'D'),
-- ── NORTHEAST ──────────────────────────────────────────────────
('GAU','VEGT','Lokpriya Gopinath Bordoloi International Airport','Guwahati','Assam','NORTHEAST','India','IN',26.1061,91.5859,'Asia/Kolkata',162,true,true,true,1,1,2900,'A'),
('DIB','VEMN','Dibrugarh Airport','Dibrugarh','Assam','NORTHEAST','India','IN',27.4839,95.0169,'Asia/Kolkata',362,true,false,true,1,1,2286,'C'),
('IXI','VELP','Lilabari Airport','Lakhimpur','Assam','NORTHEAST','India','IN',27.2955,94.0976,'Asia/Kolkata',330,true,false,true,1,1,2040,'D'),
('IXS','VEKU','Silchar Airport','Silchar','Assam','NORTHEAST','India','IN',24.9129,92.9787,'Asia/Kolkata',352,true,false,true,1,1,2285,'C'),
('TEZ','VETZ','Tezpur Airport','Tezpur','Assam','NORTHEAST','India','IN',26.7091,92.7847,'Asia/Kolkata',240,true,false,true,1,1,2286,'D'),
('JRH','VEJT','Jorhat Airport','Jorhat','Assam','NORTHEAST','India','IN',26.7315,94.1755,'Asia/Kolkata',369,true,false,true,1,1,2744,'C'),
('RUP','VERU','Rupsi Airport','Dhubri','Assam','NORTHEAST','India','IN',26.0000,89.9000,'Asia/Kolkata',130,true,false,true,1,1,1500,'E'),
('IMF','VEIM','Imphal International Airport','Imphal','Manipur','NORTHEAST','India','IN',24.7600,93.8967,'Asia/Kolkata',2539,true,true,true,1,1,2743,'B'),
('DMU','VEMR','Dimapur Airport','Dimapur','Nagaland','NORTHEAST','India','IN',25.8839,93.7712,'Asia/Kolkata',487,true,false,true,1,1,2440,'C'),
('AJL','VEAZ','Lengpui Airport','Aizawl','Mizoram','NORTHEAST','India','IN',23.8405,92.6197,'Asia/Kolkata',1629,true,false,true,1,1,2480,'C'),
('SHL','VESL','Shillong Airport','Shillong','Meghalaya','NORTHEAST','India','IN',25.7036,91.9787,'Asia/Kolkata',2910,true,false,true,1,1,1830,'D'),
('IXA','VEAT','Agartala Airport','Agartala','Tripura','NORTHEAST','India','IN',23.8870,91.2404,'Asia/Kolkata',46,true,false,true,1,1,2286,'C'),
('HGI','VEPH','Pasighat Airport','Pasighat','Arunachal Pradesh','NORTHEAST','India','IN',28.0661,95.3356,'Asia/Kolkata',477,true,false,true,1,1,1981,'D'),
('TEI','VETI','Tezu Airport','Tezu','Arunachal Pradesh','NORTHEAST','India','IN',27.9408,96.1344,'Asia/Kolkata',800,true,false,true,1,1,1600,'E'),
-- ── SOUTH ──────────────────────────────────────────────────────
('BLR','VOBL','Kempegowda International Airport','Bengaluru','Karnataka','SOUTH','India','IN',13.1986,77.7066,'Asia/Kolkata',3000,true,true,true,2,2,4000,'A'),
('MAA','VOMM','Chennai International Airport','Chennai','Tamil Nadu','SOUTH','India','IN',12.9900,80.1693,'Asia/Kolkata',52,true,true,true,4,2,3600,'A'),
('HYD','VOHS','Rajiv Gandhi International Airport','Hyderabad','Telangana','SOUTH','India','IN',17.2313,78.4298,'Asia/Kolkata',2024,true,true,true,1,2,4260,'A'),
('TRV','VOTV','Trivandrum International Airport','Thiruvananthapuram','Kerala','SOUTH','India','IN',8.4782,76.9201,'Asia/Kolkata',15,true,true,true,1,1,3400,'B'),
('COK','VOCI','Cochin International Airport','Kochi','Kerala','SOUTH','India','IN',10.1520,76.4019,'Asia/Kolkata',30,true,true,true,2,1,3400,'A'),
('CCJ','VOCL','Calicut International Airport','Kozhikode','Kerala','SOUTH','India','IN',11.1368,75.9553,'Asia/Kolkata',334,true,true,true,1,1,3050,'B'),
('CNN','VOKT','Kannur International Airport','Kannur','Kerala','SOUTH','India','IN',11.9186,75.5472,'Asia/Kolkata',328,true,true,true,1,1,3050,'B'),
('IXM','VOMD','Madurai Airport','Madurai','Tamil Nadu','SOUTH','India','IN',9.8345,78.0934,'Asia/Kolkata',459,true,false,true,1,1,2900,'B'),
('TRZ','VOTR','Tiruchirappalli International Airport','Tiruchirappalli','Tamil Nadu','SOUTH','India','IN',10.7654,78.7097,'Asia/Kolkata',88,true,true,true,1,1,2895,'B'),
('CJB','VOCB','Coimbatore International Airport','Coimbatore','Tamil Nadu','SOUTH','India','IN',11.0300,77.0434,'Asia/Kolkata',1324,true,true,true,1,1,2990,'B'),
('TIR','VOTP','Tirupati Airport','Tirupati','Andhra Pradesh','SOUTH','India','IN',13.6325,79.5433,'Asia/Kolkata',350,true,false,true,1,1,2380,'C'),
('SXV','VOSM','Salem Airport','Salem','Tamil Nadu','SOUTH','India','IN',11.7833,78.0656,'Asia/Kolkata',1017,true,false,true,1,1,1650,'D'),
('TCR','VOTK','Tuticorin Airport','Tuticorin','Tamil Nadu','SOUTH','India','IN',8.7242,77.9958,'Asia/Kolkata',129,true,false,true,1,1,1500,'D'),
('VTZ','VEVZ','Visakhapatnam Airport','Visakhapatnam','Andhra Pradesh','SOUTH','India','IN',17.7212,83.2245,'Asia/Kolkata',15,true,true,true,1,1,3200,'B'),
('VGA','VOVR','Vijayawada Airport','Vijayawada','Andhra Pradesh','SOUTH','India','IN',16.5304,80.7968,'Asia/Kolkata',82,true,false,true,1,1,3000,'B'),
('RJA','VORY','Rajahmundry Airport','Rajahmundry','Andhra Pradesh','SOUTH','India','IN',17.1103,81.8182,'Asia/Kolkata',151,true,false,true,1,1,2400,'C'),
('CDP','VOCP','Kadapa Airport','Kadapa','Andhra Pradesh','SOUTH','India','IN',14.5130,78.7728,'Asia/Kolkata',447,true,false,true,1,1,2800,'D'),
('IXE','VOMN','Mangalore International Airport','Mangalore','Karnataka','SOUTH','India','IN',12.9613,74.8904,'Asia/Kolkata',337,true,true,true,1,1,2851,'B'),
('HBX','VOHB','Hubli Airport','Hubballi','Karnataka','SOUTH','India','IN',15.3617,75.0849,'Asia/Kolkata',2171,true,false,true,1,1,2286,'C'),
('MYQ','VOYK','Mysore Airport','Mysuru','Karnataka','SOUTH','India','IN',12.2308,76.6496,'Asia/Kolkata',2469,true,false,true,1,1,1745,'C'),
('BJP','VOBG','Bellary Airport','Ballari','Karnataka','SOUTH','India','IN',15.1628,76.8828,'Asia/Kolkata',1696,true,false,true,1,1,2000,'D'),
('WGC','VOWA','Warangal Airport','Warangal','Telangana','SOUTH','India','IN',17.9144,79.6020,'Asia/Kolkata',935,true,false,true,1,1,2285,'D'),
-- ── ISLANDS ────────────────────────────────────────────────────
('IXZ','VOPB','Veer Savarkar International Airport','Port Blair','Andaman & Nicobar','ISLAND','India','IN',11.6412,92.7297,'Asia/Kolkata',14,true,false,true,1,1,3290,'B'),
('AGX','VOAT','Agatti Airport','Agatti Island','Lakshadweep','ISLAND','India','IN',10.8237,72.1760,'Asia/Kolkata',14,true,false,true,1,1,1204,'D'),
-- ── INTERNATIONAL HUBS ─────────────────────────────────────────
('DXB','OMDB','Dubai International Airport','Dubai','Dubai','INT','UAE','AE',25.2532,55.3657,'Asia/Dubai',62,false,true,true,3,3,4000,'A'),
('SIN','WSSS','Changi Airport','Singapore','Singapore','INT','Singapore','SG',1.3644,103.9915,'Asia/Singapore',22,false,true,true,4,2,4000,'A'),
('LHR','EGLL','Heathrow Airport','London','England','INT','UK','GB',51.4700,-0.4543,'Europe/London',83,false,true,true,5,2,3902,'A'),
('DOH','OTHH','Hamad International Airport','Doha','Qatar','INT','Qatar','QA',25.2731,51.6080,'Asia/Qatar',13,false,true,true,1,2,4850,'A'),
('AUH','OMAA','Abu Dhabi International Airport','Abu Dhabi','UAE','INT','UAE','AE',24.4330,54.6511,'Asia/Dubai',88,false,true,true,3,2,4100,'A'),
('BKK','VTBS','Suvarnabhumi Airport','Bangkok','Bangkok','INT','Thailand','TH',13.6900,100.7501,'Asia/Bangkok',5,false,true,true,2,2,4000,'A'),
('KUL','WMKK','Kuala Lumpur International Airport','Kuala Lumpur','Selangor','INT','Malaysia','MY',2.7456,101.7099,'Asia/Kuala_Lumpur',69,false,true,true,2,2,4019,'A'),
('JFK','KJFK','John F. Kennedy International Airport','New York','New York','INT','USA','US',40.6413,-73.7781,'America/New_York',13,false,true,true,6,4,4423,'A');

-- ============================================================
-- AIRLINES
-- ============================================================
CREATE TABLE public.airlines (
  iata_code     TEXT PRIMARY KEY,
  icao_code     TEXT,
  name          TEXT NOT NULL,
  short_name    TEXT,
  country       TEXT DEFAULT 'India',
  is_domestic   BOOLEAN DEFAULT TRUE,
  is_lowcost    BOOLEAN DEFAULT FALSE,
  hub_airport   TEXT REFERENCES public.airports(iata_code),
  website       TEXT,
  contact_phone TEXT,
  is_active     BOOLEAN DEFAULT TRUE,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO public.airlines
(iata_code,icao_code,name,short_name,country,is_domestic,is_lowcost,hub_airport,website,contact_phone)
VALUES
('AI','AIC','Air India','Air India','India',true,false,'DEL','https://airindia.com','+91-11-24622220'),
('6E','IGO','IndiGo','IndiGo','India',true,true,'DEL','https://goindigo.in','+91-99-10383838'),
('SG','SEJ','SpiceJet','SpiceJet','India',true,true,'DEL','https://spicejet.com','+91-98-71803333'),
('UK','TAI','Vistara','Vistara','India',true,false,'DEL','https://airvistara.com','+91-92-89228922'),
('IX','MDV','Air India Express','AIX','India',true,true,'COK','https://airindiaexpress.in','+91-95-55888840'),
('QP','AQP','Akasa Air','Akasa','India',true,true,'BOM','https://akasaair.com','+91-86-52001000'),
('S5','SNJ','Star Air','Star Air','India',true,false,'BLR','https://starair.in','+91-86-50009000'),
('EK','UAE','Emirates','Emirates','UAE',false,false,'DXB','https://emirates.com','+971-600555555'),
('SQ','SIA','Singapore Airlines','SIA','Singapore',false,false,'SIN','https://singaporeair.com','+65-62238888'),
('QR','QTR','Qatar Airways','Qatar Airways','Qatar',false,false,'DOH','https://qatarairways.com','+974-40221111');

-- ============================================================
-- PROFILES  (no auth.users FK — avoids Supabase editor issues)
-- ============================================================
CREATE TABLE public.profiles (
  id                  UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  email               TEXT UNIQUE NOT NULL,
  full_name           TEXT,
  display_name        TEXT,
  phone               TEXT,
  phone_verified      BOOLEAN DEFAULT FALSE,
  email_verified      BOOLEAN DEFAULT FALSE,
  date_of_birth       DATE,
  gender              TEXT,
  nationality         TEXT DEFAULT 'Indian',
  passport_number     TEXT,
  passport_expiry     DATE,
  preferred_currency  TEXT DEFAULT 'INR',
  preferred_cabin     TEXT DEFAULT 'ECONOMY',
  avatar_url          TEXT,
  notify_email        BOOLEAN DEFAULT TRUE,
  notify_sms          BOOLEAN DEFAULT TRUE,
  notify_whatsapp     BOOLEAN DEFAULT FALSE,
  notify_push         BOOLEAN DEFAULT FALSE,
  preferred_airlines  TEXT[],
  meal_preference     TEXT DEFAULT 'VEG',
  skymind_points      INT DEFAULT 0,
  tier                TEXT DEFAULT 'BLUE',
  last_login          TIMESTAMPTZ,
  login_count         INT DEFAULT 0,
  created_at          TIMESTAMPTZ DEFAULT NOW(),
  updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- USER SESSIONS
-- ============================================================
CREATE TABLE public.user_sessions (
  id          UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  user_id     UUID REFERENCES public.profiles(id) ON DELETE CASCADE,
  ip_address  TEXT,
  user_agent  TEXT,
  device_type TEXT,
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  expires_at  TIMESTAMPTZ
);

-- ============================================================
-- OTP VERIFICATIONS
-- ============================================================
CREATE TABLE public.otp_verifications (
  id         UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  user_id    UUID REFERENCES public.profiles(id) ON DELETE CASCADE,
  phone      TEXT,
  email      TEXT,
  otp_hash   TEXT NOT NULL,
  purpose    TEXT,
  is_used    BOOLEAN DEFAULT FALSE,
  attempts   INT DEFAULT 0,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- ROUTES
-- ============================================================
CREATE TABLE public.routes (
  id               UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  origin_code      TEXT NOT NULL REFERENCES public.airports(iata_code),
  destination_code TEXT NOT NULL REFERENCES public.airports(iata_code),
  distance_km      INT,
  avg_duration_min INT,
  is_active        BOOLEAN DEFAULT TRUE,
  airlines         TEXT[],
  min_price_inr    DECIMAL(10,2),
  avg_price_inr    DECIMAL(10,2),
  max_price_inr    DECIMAL(10,2),
  flights_per_day  INT DEFAULT 1,
  created_at       TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(origin_code, destination_code)
);

-- ============================================================
-- FLIGHTS
-- ============================================================
CREATE TABLE public.flights (
  id               UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  flight_number    TEXT NOT NULL,
  airline_code     TEXT REFERENCES public.airlines(iata_code),
  origin_code      TEXT REFERENCES public.airports(iata_code),
  destination_code TEXT REFERENCES public.airports(iata_code),
  departure_time   TIMESTAMPTZ NOT NULL,
  arrival_time     TIMESTAMPTZ NOT NULL,
  duration_min     INT NOT NULL,
  stops            INT DEFAULT 0,
  cabin_class      TEXT DEFAULT 'ECONOMY',
  aircraft_type    TEXT,
  total_seats      INT DEFAULT 180,
  available_seats  INT,
  status           TEXT DEFAULT 'SCHEDULED',
  terminal         TEXT,
  gate             TEXT,
  amadeus_offer_id TEXT,
  raw_offer        JSONB,
  created_at       TIMESTAMPTZ DEFAULT NOW(),
  updated_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_flights_route     ON public.flights(origin_code, destination_code);
CREATE INDEX idx_flights_departure ON public.flights(departure_time);

-- ============================================================
-- PRICE HISTORY
-- ============================================================
CREATE TABLE public.price_history (
  id               UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  origin_code      TEXT REFERENCES public.airports(iata_code),
  destination_code TEXT REFERENCES public.airports(iata_code),
  airline_code     TEXT REFERENCES public.airlines(iata_code),
  cabin_class      TEXT DEFAULT 'ECONOMY',
  price            DECIMAL(10,2) NOT NULL,
  currency         TEXT DEFAULT 'INR',
  departure_date   DATE NOT NULL,
  days_until_dep   INT,
  day_of_week      INT,
  month            INT,
  is_holiday       BOOLEAN DEFAULT FALSE,
  recorded_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ph_route ON public.price_history(origin_code, destination_code);
CREATE INDEX idx_ph_date  ON public.price_history(departure_date);

-- ============================================================
-- BOOKINGS
-- ============================================================
CREATE TABLE public.bookings (
  id                    UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  booking_reference     TEXT UNIQUE NOT NULL,
  user_id               UUID REFERENCES public.profiles(id),
  flight_id             UUID REFERENCES public.flights(id),
  amadeus_booking_id    TEXT,
  status                TEXT DEFAULT 'PENDING',
  total_price           DECIMAL(10,2) NOT NULL,
  base_fare             DECIMAL(10,2),
  taxes                 DECIMAL(10,2),
  currency              TEXT DEFAULT 'INR',
  cabin_class           TEXT DEFAULT 'ECONOMY',
  payment_status        TEXT DEFAULT 'UNPAID',
  payment_method        TEXT,
  payment_id            TEXT,
  razorpay_order_id     TEXT,
  razorpay_signature    TEXT,
  confirmation_sent     BOOLEAN DEFAULT FALSE,
  checkin_notif_sent    BOOLEAN DEFAULT FALSE,
  flight_offer_data     JSONB,
  contact_email         TEXT,
  contact_phone         TEXT,
  coupon_code           TEXT,
  discount_amount       DECIMAL(10,2) DEFAULT 0,
  skymind_points_used   INT DEFAULT 0,
  skymind_points_earned INT DEFAULT 0,
  created_at            TIMESTAMPTZ DEFAULT NOW(),
  updated_at            TIMESTAMPTZ DEFAULT NOW(),
  cancelled_at          TIMESTAMPTZ,
  cancellation_reason   TEXT
);

CREATE INDEX idx_bookings_user   ON public.bookings(user_id);
CREATE INDEX idx_bookings_ref    ON public.bookings(booking_reference);
CREATE INDEX idx_bookings_status ON public.bookings(status);

-- ============================================================
-- PASSENGERS
-- ============================================================
CREATE TABLE public.passengers (
  id               UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  booking_id       UUID REFERENCES public.bookings(id) ON DELETE CASCADE,
  type             TEXT DEFAULT 'ADULT',
  title            TEXT,
  first_name       TEXT NOT NULL,
  last_name        TEXT NOT NULL,
  date_of_birth    DATE,
  gender           TEXT,
  nationality      TEXT,
  passport_number  TEXT,
  passport_expiry  DATE,
  seat_number      TEXT,
  meal_preference  TEXT DEFAULT 'VEG',
  baggage_kg       INT DEFAULT 15,
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- NOTIFICATIONS
-- ============================================================
CREATE TABLE public.notifications (
  id            UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  user_id       UUID REFERENCES public.profiles(id) ON DELETE CASCADE,
  booking_id    UUID REFERENCES public.bookings(id),
  type          TEXT NOT NULL,
  channel       TEXT NOT NULL,
  recipient     TEXT NOT NULL,
  subject       TEXT,
  message       TEXT NOT NULL,
  template_id   TEXT,
  status        TEXT DEFAULT 'PENDING',
  provider      TEXT,
  provider_id   TEXT,
  error_message TEXT,
  retry_count   INT DEFAULT 0,
  scheduled_at  TIMESTAMPTZ DEFAULT NOW(),
  sent_at       TIMESTAMPTZ,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_notif_user      ON public.notifications(user_id);
CREATE INDEX idx_notif_status    ON public.notifications(status);
CREATE INDEX idx_notif_scheduled ON public.notifications(scheduled_at);

-- ============================================================
-- PRICE ALERTS
-- ============================================================
CREATE TABLE public.price_alerts (
  id               UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  user_id          UUID REFERENCES public.profiles(id) ON DELETE CASCADE,
  origin_code      TEXT REFERENCES public.airports(iata_code),
  destination_code TEXT REFERENCES public.airports(iata_code),
  departure_date   DATE NOT NULL,
  return_date      DATE,
  cabin_class      TEXT DEFAULT 'ECONOMY',
  adults           INT DEFAULT 1,
  target_price     DECIMAL(10,2) NOT NULL,
  currency         TEXT DEFAULT 'INR',
  is_active        BOOLEAN DEFAULT TRUE,
  notify_email     BOOLEAN DEFAULT TRUE,
  notify_sms       BOOLEAN DEFAULT TRUE,
  notify_whatsapp  BOOLEAN DEFAULT FALSE,
  last_checked     TIMESTAMPTZ,
  last_price       DECIMAL(10,2),
  triggered_count  INT DEFAULT 0,
  triggered_at     TIMESTAMPTZ,
  expires_at       TIMESTAMPTZ,
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- SAVED SEARCHES
-- ============================================================
CREATE TABLE public.saved_searches (
  id               UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  user_id          UUID REFERENCES public.profiles(id) ON DELETE CASCADE,
  origin_code      TEXT REFERENCES public.airports(iata_code),
  destination_code TEXT REFERENCES public.airports(iata_code),
  departure_date   DATE,
  adults           INT DEFAULT 1,
  cabin_class      TEXT DEFAULT 'ECONOMY',
  search_count     INT DEFAULT 1,
  last_searched    TIMESTAMPTZ DEFAULT NOW(),
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- COUPONS
-- ============================================================
CREATE TABLE public.coupons (
  id              UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  code            TEXT UNIQUE NOT NULL,
  description     TEXT,
  discount_type   TEXT,
  discount_value  DECIMAL(10,2),
  max_discount    DECIMAL(10,2),
  min_booking     DECIMAL(10,2) DEFAULT 0,
  usage_limit     INT,
  used_count      INT DEFAULT 0,
  valid_from      TIMESTAMPTZ DEFAULT NOW(),
  valid_until     TIMESTAMPTZ,
  is_active       BOOLEAN DEFAULT TRUE,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO public.coupons (code,description,discount_type,discount_value,max_discount,min_booking,usage_limit,valid_until)
VALUES
('SKYMIND10','10% off first booking','PERCENT',10,1500,3000,1000,NOW()+INTERVAL '1 year'),
('FLAT500','Flat Rs.500 off','FLAT',500,500,2000,500,NOW()+INTERVAL '6 months'),
('NEWUSER','15% off for new users','PERCENT',15,2000,1000,999,NOW()+INTERVAL '1 year');

-- ============================================================
-- ROW LEVEL SECURITY
-- ============================================================
ALTER TABLE public.airports         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.airlines         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.routes           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.flights          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.price_history    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coupons          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profiles         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.bookings         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.passengers       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.price_alerts     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.saved_searches   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_sessions    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.otp_verifications ENABLE ROW LEVEL SECURITY;

-- Public read (airports, routes, etc.)
CREATE POLICY "pub_airports"  ON public.airports      FOR SELECT USING (true);
CREATE POLICY "pub_airlines"  ON public.airlines      FOR SELECT USING (true);
CREATE POLICY "pub_routes"    ON public.routes        FOR SELECT USING (true);
CREATE POLICY "pub_flights"   ON public.flights       FOR SELECT USING (true);
CREATE POLICY "pub_ph"        ON public.price_history FOR SELECT USING (true);
CREATE POLICY "pub_coupons"   ON public.coupons       FOR SELECT USING (is_active = true);

-- Profiles — users manage their own
CREATE POLICY "profiles_sel" ON public.profiles FOR SELECT USING (auth.uid() = id);
CREATE POLICY "profiles_ins" ON public.profiles FOR INSERT WITH CHECK (auth.uid() = id);
CREATE POLICY "profiles_upd" ON public.profiles FOR UPDATE USING (auth.uid() = id);

-- Bookings
CREATE POLICY "bookings_sel" ON public.bookings FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "bookings_ins" ON public.bookings FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "bookings_upd" ON public.bookings FOR UPDATE USING (auth.uid() = user_id);

-- Passengers
CREATE POLICY "passengers_sel" ON public.passengers FOR SELECT
  USING (booking_id IN (SELECT id FROM public.bookings WHERE user_id = auth.uid()));
CREATE POLICY "passengers_ins" ON public.passengers FOR INSERT
  WITH CHECK (booking_id IN (SELECT id FROM public.bookings WHERE user_id = auth.uid()));

-- Others — user owns
CREATE POLICY "alerts_all"    ON public.price_alerts    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "searches_all"  ON public.saved_searches  FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "notif_sel"     ON public.notifications   FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "sessions_sel"  ON public.user_sessions   FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "otp_all"       ON public.otp_verifications FOR ALL USING (auth.uid() = user_id);

-- ============================================================
-- ROUTES DATA
-- ============================================================
INSERT INTO public.routes
(origin_code,destination_code,distance_km,avg_duration_min,airlines,min_price_inr,avg_price_inr,max_price_inr,flights_per_day)
VALUES
-- DEL hub
('DEL','BOM',1148,120,'{AI,6E,SG,UK,QP}',2799,6200,18000,32),
('DEL','BLR',1740,155,'{AI,6E,SG,UK,QP}',3299,7000,20000,26),
('DEL','MAA',1760,160,'{AI,6E,SG,UK,QP}',3499,7500,22000,20),
('DEL','HYD',1253,130,'{AI,6E,SG,UK,QP}',3099,6600,19000,22),
('DEL','CCU',1305,130,'{AI,6E,SG,UK}',2999,5900,17000,18),
('DEL','COK',2210,195,'{AI,6E,SG}',4299,9000,26000,10),
('DEL','GOI',1892,175,'{AI,6E,SG,UK}',3799,8200,24000,10),
('DEL','JAI',258,55,'{AI,6E,SG,UK,QP}',1399,3100,9000,16),
('DEL','LKO',492,65,'{AI,6E,SG,UK}',1599,3600,10000,14),
('DEL','AMD',909,90,'{AI,6E,SG,UK,QP}',2099,4600,13000,12),
('DEL','ATQ',440,65,'{AI,6E,SG}',1499,3200,9500,8),
('DEL','IXC',247,50,'{AI,6E,SG}',1199,2700,8000,10),
('DEL','SXR',890,80,'{AI,6E,SG}',2399,5000,15000,10),
('DEL','IXJ',560,65,'{AI,6E,SG}',1699,3700,10500,8),
('DEL','IXL',1054,85,'{AI,6E}',2999,5800,16500,6),
('DEL','DED',267,55,'{AI,6E}',1299,2900,8200,6),
('DEL','GAU',1580,150,'{AI,6E,SG}',3499,7300,21000,8),
('DEL','BBI',1610,150,'{AI,6E,SG}',3199,6700,18500,8),
('DEL','VNS',676,75,'{AI,6E,SG}',1799,4000,11000,8),
('DEL','PAT',990,100,'{AI,6E,SG}',2199,4700,13500,10),
('DEL','IXR',1260,125,'{AI,6E}',2799,5700,16000,6),
('DEL','BHO',697,80,'{AI,6E,SG}',1899,4100,11500,6),
('DEL','IDR',778,85,'{AI,6E,SG}',1999,4300,12000,6),
('DEL','NAG',1083,115,'{AI,6E,SG}',2299,4900,13800,6),
('DEL','RPR',1120,115,'{AI,6E}',2499,5200,14500,4),
('DEL','TRV',2240,205,'{AI,6E}',4599,9600,27000,4),
('DEL','IXZ',2008,183,'{AI,6E}',4099,8700,24500,4),
('DEL','VTZ',1393,132,'{AI,6E,SG}',2999,6200,17500,6),
('DEL','IMF',2098,188,'{AI,6E}',3999,8100,22500,4),
('DEL','JDH',596,70,'{AI,6E,SG}',1799,3800,10800,4),
('DEL','UDR',654,75,'{AI,6E}',1899,4000,11300,4),
('DEL','PNQ',1397,130,'{AI,6E,SG,UK}',2999,6000,17000,10),
-- BOM hub
('BOM','BLR',845,85,'{AI,6E,SG,UK,QP}',2399,5100,15000,26),
('BOM','MAA',1040,100,'{AI,6E,SG,UK,QP}',2599,5400,16000,20),
('BOM','HYD',621,70,'{AI,6E,SG,UK,QP}',2099,4400,13000,22),
('BOM','CCU',1658,155,'{AI,6E,SG,UK}',3399,7100,21000,14),
('BOM','COK',1209,115,'{AI,6E,SG,UK}',2799,5700,17000,14),
('BOM','GOI',467,55,'{AI,6E,SG,UK,QP}',1699,3600,10500,12),
('BOM','MYA',536,65,'{AI,6E,SG,QP}',1799,3800,10900,8),
('BOM','AMD',471,60,'{AI,6E,SG,UK,QP}',1499,3200,9500,16),
('BOM','PNQ',119,40,'{AI,6E,SG}',899,2100,7000,10),
('BOM','JAI',1050,105,'{AI,6E,SG,UK}',2399,5000,14000,8),
('BOM','IDR',509,65,'{AI,6E,SG}',1699,3600,10500,6),
('BOM','NAG',830,85,'{AI,6E,SG}',2199,4600,13000,8),
('BOM','TRV',1383,127,'{AI,6E,SG}',2999,6100,17500,8),
('BOM','TRZ',1296,123,'{AI,6E}',2899,5900,16800,4),
('BOM','CJB',979,101,'{AI,6E,SG}',2299,4800,13700,6),
('BOM','IXE',340,53,'{AI,6E,IX}',1199,2600,7500,8),
('BOM','IXZ',2136,197,'{AI,6E}',4199,8600,24200,2),
('BOM','BBI',1648,153,'{AI,6E,SG}',3399,6900,19500,6),
('BOM','LKO',1177,115,'{AI,6E,SG}',2699,5500,15500,6),
('BOM','PAT',1570,146,'{AI,6E}',3299,6700,18900,4),
('BOM','GAU',2147,198,'{AI,6E}',4199,8600,24000,4),
-- BLR hub
('BLR','MAA',290,50,'{AI,6E,SG,UK,QP}',1199,2600,8000,22),
('BLR','HYD',498,60,'{AI,6E,SG,UK,QP}',1399,3000,9000,20),
('BLR','CCU',1560,148,'{AI,6E,SG}',3299,6700,19000,10),
('BLR','COK',360,55,'{AI,6E,SG,UK,IX}',1299,2800,8500,16),
('BLR','TRV',218,45,'{AI,6E,SG,IX}',1099,2400,7400,12),
('BLR','TRZ',275,50,'{AI,6E,SG}',1199,2600,7800,8),
('BLR','IXM',369,55,'{AI,6E}',1399,3000,8800,6),
('BLR','CJB',247,50,'{AI,6E,SG}',1099,2400,7200,8),
('BLR','IXE',225,45,'{AI,6E,IX}',1099,2400,7200,8),
('BLR','MYQ',143,38,'{AI,6E}',999,2200,6700,6),
('BLR','VTZ',645,75,'{AI,6E}',1899,4000,11500,6),
('BLR','VGA',625,72,'{AI,6E}',1799,3800,10800,4),
('BLR','TIR',286,52,'{AI,6E}',1199,2600,7800,6),
('BLR','GOI',548,65,'{AI,6E,SG}',1699,3600,10500,8),
('BLR','NAG',966,100,'{AI,6E}',2299,4700,13300,4),
('BLR','BBI',1067,110,'{AI,6E}',2499,5100,14400,4),
('BLR','GAU',2082,193,'{AI,6E}',4099,8400,23600,4),
-- MAA hub
('MAA','HYD',521,63,'{AI,6E,SG,UK,QP}',1499,3200,9500,16),
('MAA','CCU',1369,132,'{AI,6E,SG}',2899,5900,17000,10),
('MAA','COK',520,63,'{AI,6E,SG,IX}',1599,3400,10000,12),
('MAA','TRV',450,60,'{AI,6E,SG,IX}',1399,2900,9000,10),
('MAA','TRZ',315,52,'{AI,6E,SG}',1199,2600,7800,8),
('MAA','IXM',330,53,'{AI,6E}',1299,2800,8300,6),
('MAA','CJB',493,63,'{AI,6E}',1599,3400,9700,8),
('MAA','VTZ',592,70,'{AI,6E}',1799,3800,10700,6),
('MAA','TIR',181,42,'{AI,6E}',899,2000,6200,6),
('MAA','BBI',1066,110,'{AI,6E}',2499,5100,14400,6),
('MAA','IXZ',1372,132,'{AI,6E}',2999,6100,17300,4),
-- HYD hub
('HYD','CCU',1285,127,'{AI,6E,SG}',2799,5700,16200,8),
('HYD','COK',884,90,'{AI,6E,SG}',2099,4500,12800,8),
('HYD','VTZ',347,53,'{AI,6E,SG}',1399,3000,8800,8),
('HYD','VGA',275,50,'{AI,6E}',1199,2600,7700,6),
('HYD','NAG',629,73,'{AI,6E}',1899,4000,11300,6),
('HYD','BBI',1010,105,'{AI,6E}',2399,4900,13900,6),
('HYD','WGC',151,37,'{AI,6E}',899,2000,6200,4),
('HYD','TRV',1115,112,'{AI,6E}',2599,5300,15000,6),
-- CCU hub
('CCU','GAU',430,60,'{AI,6E,SG}',1599,3400,9700,12),
('CCU','IXB',583,70,'{AI,6E}',1799,3800,10800,6),
('CCU','PAT',513,65,'{AI,6E}',1699,3600,10200,6),
('CCU','BBI',440,60,'{AI,6E,SG}',1499,3200,9200,8),
('CCU','IXR',341,55,'{AI,6E,SG}',1399,3000,8700,6),
('CCU','IMF',1006,105,'{AI,6E}',2399,4900,13900,4),
('CCU','IXA',359,57,'{AI,6E}',1499,3200,9200,6),
('CCU','DIB',614,73,'{AI,6E}',1799,3800,10800,4),
('CCU','IXZ',1255,122,'{AI,6E}',2899,5900,16700,4),
-- COK hub
('COK','TRV',215,42,'{AI,6E,SG,IX}',899,2000,6300,12),
('COK','TRZ',410,57,'{6E,SG,IX}',1299,2800,8300,6),
('COK','IXE',190,40,'{AI,6E,IX}',899,2000,6200,6),
('COK','CJB',165,38,'{AI,6E}',899,2000,6200,4),
('COK','CCJ',183,42,'{AI,6E,IX}',899,2000,6300,8),
('COK','CNN',233,47,'{AI,6E,IX}',1099,2400,7200,6),
('COK','AGX',1241,120,'{AI,IX}',2799,5700,16100,4),
-- AMD hub
('AMD','JAI',562,68,'{AI,6E,SG}',1699,3600,10300,6),
('AMD','IDR',295,52,'{AI,6E}',1199,2600,7700,4),
('AMD','UDR',241,47,'{AI,6E}',1099,2400,7200,4),
('AMD','BDQ',106,33,'{AI,6E}',699,1700,5400,6),
('AMD','BHJ',293,52,'{AI,6E}',1199,2600,7700,4),
('AMD','JDH',494,64,'{AI,6E}',1599,3400,9700,4),
-- GAU/Northeast
('GAU','IMF',499,66,'{AI,6E}',1699,3600,10300,4),
('GAU','IXA',326,53,'{AI,6E}',1299,2800,8200,4),
('GAU','DIB',439,61,'{AI,6E}',1599,3400,9700,4),
('GAU','IXS',370,57,'{AI,6E}',1499,3200,9200,4),
('GAU','DMU',446,62,'{AI,6E}',1599,3400,9700,4),
('GAU','TEZ',174,40,'{AI,6E}',899,2000,6200,4),
('GAU','JRH',311,53,'{AI,6E}',1299,2800,8200,4),
('GAU','IXI',287,51,'{AI,6E}',1199,2600,7700,4),
('GAU','SHL',102,33,'{AI,6E}',799,1900,5900,4),
('GAU','IXB',284,51,'{AI,6E}',1199,2600,7700,4),
-- South cluster
('TRV','CJB',399,58,'{AI,6E}',1499,3200,9200,4),
('TRV','TRZ',273,50,'{AI,6E}',1099,2400,7200,4),
('CJB','TRZ',220,44,'{AI,6E}',999,2200,6700,4),
('CJB','CCJ',248,48,'{AI,6E,IX}',1099,2400,7200,4),
('TRZ','IXM',101,32,'{AI,6E}',699,1700,5400,4),
('CCJ','CNN',136,36,'{AI,6E,IX}',799,1900,5900,6),
('VGA','VTZ',214,44,'{AI,6E}',999,2200,6700,4),
('IXE','GOI',439,62,'{AI,6E}',1599,3400,9700,4),
('IXE','HBX',147,37,'{AI,6E}',799,1900,5900,4),
-- J&K/Ladakh
('IXJ','SXR',301,52,'{AI,6E}',1199,2600,7700,4),
('IXJ','IXL',432,62,'{AI,6E}',1599,3400,9700,2),
('SXR','IXL',288,51,'{AI,6E}',1099,2400,7200,4),
('SXR','ATQ',330,53,'{AI,6E}',1299,2800,8200,4),
('ATQ','IXC',115,35,'{AI,6E}',699,1700,5400,4),
-- Rajasthan
('JAI','JDH',277,51,'{AI,6E}',1099,2400,7200,4),
('JAI','UDR',403,59,'{AI,6E}',1499,3200,9200,2),
-- MP/CG/Bihar
('BHO','IDR',189,42,'{AI,6E}',899,2000,6200,4),
('BHO','NAG',354,56,'{AI,6E}',1399,3000,8700,2),
('PAT','IXR',294,52,'{AI,6E}',1199,2600,7700,4),
('PAT','GAY',150,38,'{AI,6E}',799,1900,5900,4),
('BBI','RPR',430,61,'{AI,6E}',1599,3400,9700,4),
('BBI','IXR',441,61,'{AI,6E}',1599,3400,9700,4),
('RPR','NAG',452,62,'{AI,6E}',1599,3400,9700,2),
-- Islands
('IXZ','BOM',2136,197,'{AI,6E}',4199,8600,24200,2),
('IXZ','BLR',1764,163,'{AI,6E}',3599,7300,20600,2),
('IXZ','HYD',1701,158,'{AI,6E}',3499,7100,20000,2),
('AGX','COK',1241,120,'{AI,IX}',2799,5700,16100,4),
('AGX','MAA',1636,152,'{AI,IX}',3299,6700,18900,2),
-- GOI extras
('GOI','MAA',1009,104,'{AI,6E,SG}',2399,4900,13900,4),
('GOI','HYD',525,66,'{AI,6E,SG}',1699,3600,10200,4),
-- Northeast extras
('IMF','DMU',259,49,'{AI,6E}',1099,2400,7200,2),
('DIB','JRH',145,37,'{AI,6E}',799,1900,5900,2),
('IXA','SHL',355,56,'{AI,6E}',1399,3000,8700,2)
ON CONFLICT (origin_code,destination_code) DO UPDATE SET
  airlines=EXCLUDED.airlines,
  min_price_inr=EXCLUDED.min_price_inr,
  avg_price_inr=EXCLUDED.avg_price_inr,
  max_price_inr=EXCLUDED.max_price_inr,
  flights_per_day=EXCLUDED.flights_per_day;

-- Auto-add reverse routes
INSERT INTO public.routes
(origin_code,destination_code,distance_km,avg_duration_min,airlines,min_price_inr,avg_price_inr,max_price_inr,flights_per_day)
SELECT destination_code,origin_code,distance_km,avg_duration_min,airlines,min_price_inr,avg_price_inr,max_price_inr,flights_per_day
FROM public.routes
ON CONFLICT (origin_code,destination_code) DO NOTHING;

-- ============================================================
-- VIEWS
-- ============================================================
CREATE VIEW public.v_booking_details AS
SELECT b.id, b.booking_reference, b.status, b.payment_status,
       b.total_price, b.currency, b.cabin_class,
       b.contact_email, b.contact_phone, b.checkin_notif_sent, b.created_at,
       p.full_name AS user_name, p.notify_email, p.notify_sms, p.notify_whatsapp,
       b.flight_offer_data
FROM public.bookings b
JOIN public.profiles p ON b.user_id = p.id;

CREATE VIEW public.v_pending_notifications AS
SELECT * FROM public.notifications
WHERE status = 'PENDING' AND scheduled_at <= NOW() AND retry_count < 3
ORDER BY scheduled_at ASC LIMIT 100;

CREATE VIEW public.v_active_alerts AS
SELECT pa.*, p.full_name, p.email, p.phone,
       p.notify_email, p.notify_sms, p.notify_whatsapp,
       ao.city AS origin_city, ad.city AS dest_city
FROM public.price_alerts pa
JOIN public.profiles p ON pa.user_id = p.id
JOIN public.airports ao ON pa.origin_code = ao.iata_code
JOIN public.airports ad ON pa.destination_code = ad.iata_code
WHERE pa.is_active = TRUE AND (pa.expires_at IS NULL OR pa.expires_at > NOW());

CREATE VIEW public.v_domestic_routes AS
SELECT r.origin_code, ao.city AS origin_city, ao.state AS origin_state,
       r.destination_code, ad.city AS dest_city, ad.state AS dest_state,
       r.distance_km, r.avg_duration_min, r.airlines,
       r.min_price_inr, r.avg_price_inr, r.flights_per_day
FROM public.routes r
JOIN public.airports ao ON r.origin_code = ao.iata_code
JOIN public.airports ad ON r.destination_code = ad.iata_code
WHERE ao.country_code = 'IN' AND ad.country_code = 'IN'
ORDER BY r.flights_per_day DESC;

-- ============================================================
-- VERIFY
-- ============================================================
SELECT
  (SELECT COUNT(*) FROM public.airports WHERE country_code='IN') AS indian_airports,
  (SELECT COUNT(*) FROM public.airlines) AS airlines,
  (SELECT COUNT(*) FROM public.routes)   AS total_routes;
