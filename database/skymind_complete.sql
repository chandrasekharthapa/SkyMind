-- ================================================================
-- SkyMind — Complete Production Database (Single File, Verified)
-- Works on Supabase free tier. Run once in SQL Editor.
-- ================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ================================================================
-- STEP 1: DROP EVERYTHING (safe re-run)
-- ================================================================
DROP VIEW  IF EXISTS public.v_domestic_routes       CASCADE;
DROP VIEW  IF EXISTS public.v_active_alerts         CASCADE;
DROP VIEW  IF EXISTS public.v_pending_notifications CASCADE;
DROP VIEW  IF EXISTS public.v_booking_details       CASCADE;
DROP TABLE IF EXISTS public.otp_verifications       CASCADE;
DROP TABLE IF EXISTS public.notifications           CASCADE;
DROP TABLE IF EXISTS public.passengers              CASCADE;
DROP TABLE IF EXISTS public.bookings                CASCADE;
DROP TABLE IF EXISTS public.price_alerts            CASCADE;
DROP TABLE IF EXISTS public.saved_searches          CASCADE;
DROP TABLE IF EXISTS public.price_history           CASCADE;
DROP TABLE IF EXISTS public.flights                 CASCADE;
DROP TABLE IF EXISTS public.coupons                 CASCADE;
DROP TABLE IF EXISTS public.user_sessions           CASCADE;
DROP TABLE IF EXISTS public.profiles                CASCADE;
DROP TABLE IF EXISTS public.routes                  CASCADE;
DROP TABLE IF EXISTS public.airlines                CASCADE;
DROP TABLE IF EXISTS public.airports                CASCADE;
DROP FUNCTION IF EXISTS public.handle_new_user()          CASCADE;
DROP FUNCTION IF EXISTS public.update_updated_at()        CASCADE;
DROP FUNCTION IF EXISTS public.handle_booking_confirmed() CASCADE;
DROP FUNCTION IF EXISTS public.gen_booking_ref()          CASCADE;
DROP FUNCTION IF EXISTS public.expire_old_alerts()        CASCADE;

-- ================================================================
-- STEP 2: AIRPORTS
-- ================================================================
CREATE TABLE public.airports (
  iata_code        TEXT PRIMARY KEY,
  icao_code        TEXT UNIQUE,
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

INSERT INTO public.airports (iata_code,icao_code,name,city,state,region,country,country_code,latitude,longitude,timezone,elevation_ft,is_domestic,is_international,is_active,terminal_count,runway_count,longest_runway_m,aai_category) VALUES
('DEL','VIDP','Indira Gandhi International Airport','New Delhi','Delhi','NORTH','India','IN',28.5665,77.1031,'Asia/Kolkata',777,TRUE,TRUE,TRUE,3,3,4430,'A'),
('ATQ','VIAR','Sri Guru Ram Dass Jee International Airport','Amritsar','Punjab','NORTH','India','IN',31.7096,74.7973,'Asia/Kolkata',756,TRUE,TRUE,TRUE,1,1,3200,'B'),
('IXC','VICG','Chandigarh International Airport','Chandigarh','Chandigarh','NORTH','India','IN',30.6735,76.7885,'Asia/Kolkata',1012,TRUE,FALSE,TRUE,1,1,2740,'B'),
('LUH','VILD','Ludhiana Airport','Ludhiana','Punjab','NORTH','India','IN',30.8547,75.9526,'Asia/Kolkata',834,TRUE,FALSE,TRUE,1,1,1800,'D'),
('BUP','VIBT','Bathinda Airport','Bathinda','Punjab','NORTH','India','IN',30.2701,74.7557,'Asia/Kolkata',663,TRUE,FALSE,TRUE,1,1,2750,'D'),
('IXJ','VIJU','Jammu Airport','Jammu','J&K','NORTH','India','IN',32.6891,74.8374,'Asia/Kolkata',1029,TRUE,FALSE,TRUE,1,1,2895,'B'),
('SXR','VISR','Sheikh ul-Alam International Airport','Srinagar','J&K','NORTH','India','IN',33.9871,74.7742,'Asia/Kolkata',5429,TRUE,FALSE,TRUE,1,1,3050,'B'),
('IXL','VILH','Kushok Bakula Rimpochhe Airport','Leh','Ladakh','NORTH','India','IN',34.1359,77.5465,'Asia/Kolkata',10682,TRUE,FALSE,TRUE,1,1,3354,'C'),
('DED','VIDN','Jolly Grant Airport','Dehradun','Uttarakhand','NORTH','India','IN',30.1897,78.1803,'Asia/Kolkata',1796,TRUE,FALSE,TRUE,1,1,2398,'C'),
('PGH','VIPC','Pantnagar Airport','Pantnagar','Uttarakhand','NORTH','India','IN',29.0334,79.4737,'Asia/Kolkata',799,TRUE,FALSE,TRUE,1,1,1500,'D'),
('DHM','VIDD','Kangra Gaggal Airport','Dharamshala','Himachal Pradesh','NORTH','India','IN',32.1651,76.2634,'Asia/Kolkata',2525,TRUE,FALSE,TRUE,1,1,1372,'D'),
('KUU','VIKU','Bhuntar Airport','Kullu','Himachal Pradesh','NORTH','India','IN',31.8767,77.1544,'Asia/Kolkata',3038,TRUE,FALSE,TRUE,1,1,1150,'E'),
('SLV','VISL','Shimla Airport','Shimla','Himachal Pradesh','NORTH','India','IN',31.0818,77.068,'Asia/Kolkata',5072,TRUE,FALSE,TRUE,1,1,1180,'E'),
('LKO','VILK','Chaudhary Charan Singh International Airport','Lucknow','Uttar Pradesh','NORTH','India','IN',26.7606,80.8893,'Asia/Kolkata',410,TRUE,TRUE,TRUE,1,2,2743,'A'),
('VNS','VIBN','Lal Bahadur Shastri International Airport','Varanasi','Uttar Pradesh','NORTH','India','IN',25.4524,82.8593,'Asia/Kolkata',266,TRUE,FALSE,TRUE,1,1,2743,'B'),
('AGR','VIAG','Agra Airport','Agra','Uttar Pradesh','NORTH','India','IN',27.1558,77.9609,'Asia/Kolkata',551,TRUE,FALSE,TRUE,1,1,2745,'C'),
('IXD','VIAL','Bamrauli Airport','Prayagraj','Uttar Pradesh','NORTH','India','IN',25.4401,81.7339,'Asia/Kolkata',322,TRUE,FALSE,TRUE,1,1,2743,'C'),
('KNU','VIKG','Chakeri Airport','Kanpur','Uttar Pradesh','NORTH','India','IN',26.4044,80.3649,'Asia/Kolkata',410,TRUE,FALSE,TRUE,1,1,2745,'D'),
('GOP','VEGP','Gorakhpur Airport','Gorakhpur','Uttar Pradesh','NORTH','India','IN',26.7397,83.4497,'Asia/Kolkata',259,TRUE,FALSE,TRUE,1,1,2744,'C'),
('JAI','VIJP','Jaipur International Airport','Jaipur','Rajasthan','NORTH','India','IN',26.8242,75.8122,'Asia/Kolkata',1263,TRUE,TRUE,TRUE,2,2,3405,'A'),
('JDH','VEJD','Jodhpur Airport','Jodhpur','Rajasthan','NORTH','India','IN',26.2511,73.0489,'Asia/Kolkata',717,TRUE,FALSE,TRUE,1,1,3048,'B'),
('UDR','VAUD','Maharana Pratap Airport','Udaipur','Rajasthan','NORTH','India','IN',24.6177,73.8961,'Asia/Kolkata',1684,TRUE,FALSE,TRUE,1,1,2286,'C'),
('JSA','VIJS','Jaisalmer Airport','Jaisalmer','Rajasthan','NORTH','India','IN',26.8887,70.865,'Asia/Kolkata',751,TRUE,FALSE,TRUE,1,1,3048,'D'),
('BKB','VIBK','Nal Airport','Bikaner','Rajasthan','NORTH','India','IN',28.0706,73.2072,'Asia/Kolkata',750,TRUE,FALSE,TRUE,1,1,2743,'D'),
('GBD','VIGR','Gwalior Airport','Gwalior','Madhya Pradesh','CENTRAL','India','IN',26.2933,78.2278,'Asia/Kolkata',617,TRUE,FALSE,TRUE,1,1,2745,'C'),
('BOM','VABB','Chhatrapati Shivaji Maharaj International Airport','Mumbai','Maharashtra','WEST','India','IN',19.0896,72.8656,'Asia/Kolkata',37,TRUE,TRUE,TRUE,2,2,3660,'A'),
('PNQ','VAPO','Pune Airport','Pune','Maharashtra','WEST','India','IN',18.5821,73.9197,'Asia/Kolkata',1942,TRUE,FALSE,TRUE,1,1,2743,'B'),
('NAG','VANP','Dr. Babasaheb Ambedkar International Airport','Nagpur','Maharashtra','WEST','India','IN',21.0922,79.0473,'Asia/Kolkata',1033,TRUE,TRUE,TRUE,1,1,3200,'B'),
('GOI','VAGO','Goa International Airport','South Goa','Goa','WEST','India','IN',15.3808,73.8314,'Asia/Kolkata',150,TRUE,TRUE,TRUE,1,1,3328,'B'),
('MYA','VOMY','Mopa International Airport','North Goa','Goa','WEST','India','IN',15.7127,73.8651,'Asia/Kolkata',200,TRUE,TRUE,TRUE,1,1,4000,'B'),
('KLH','VAKP','Kolhapur Airport','Kolhapur','Maharashtra','WEST','India','IN',16.6647,74.2894,'Asia/Kolkata',1981,TRUE,FALSE,TRUE,1,1,1800,'D'),
('ISK','VANR','Nashik-Ozar Airport','Nashik','Maharashtra','WEST','India','IN',20.1192,73.9128,'Asia/Kolkata',1959,TRUE,FALSE,TRUE,1,1,3048,'C'),
('SSE','VASO','Solapur Airport','Solapur','Maharashtra','WEST','India','IN',17.628,75.9348,'Asia/Kolkata',1584,TRUE,FALSE,TRUE,1,1,1800,'D'),
('SAG','VAND','Shirdi Airport','Shirdi','Maharashtra','WEST','India','IN',19.6888,74.379,'Asia/Kolkata',1984,TRUE,FALSE,TRUE,1,1,3600,'C'),
('QJV','VAAB','Aurangabad Airport','Aurangabad','Maharashtra','WEST','India','IN',19.8627,75.3981,'Asia/Kolkata',1912,TRUE,FALSE,TRUE,1,1,2953,'C'),
('AMD','VAAH','Sardar Vallabhbhai Patel International Airport','Ahmedabad','Gujarat','WEST','India','IN',23.0772,72.6347,'Asia/Kolkata',189,TRUE,TRUE,TRUE,2,2,3200,'A'),
('BDQ','VABO','Vadodara Airport','Vadodara','Gujarat','WEST','India','IN',22.3362,73.2263,'Asia/Kolkata',129,TRUE,FALSE,TRUE,1,1,2745,'B'),
('STV','VASU','Surat Airport','Surat','Gujarat','WEST','India','IN',21.1141,72.7418,'Asia/Kolkata',16,TRUE,FALSE,TRUE,1,1,2905,'B'),
('RAJ','VARK','Rajkot Airport','Rajkot','Gujarat','WEST','India','IN',22.3092,70.7796,'Asia/Kolkata',441,TRUE,FALSE,TRUE,1,1,2750,'C'),
('JGA','VAJI','Jamnagar Airport','Jamnagar','Gujarat','WEST','India','IN',22.4655,70.0126,'Asia/Kolkata',69,TRUE,FALSE,TRUE,1,1,2743,'C'),
('BHJ','VABJ','Bhuj Airport','Bhuj','Gujarat','WEST','India','IN',23.2878,69.6701,'Asia/Kolkata',268,TRUE,FALSE,TRUE,1,1,3500,'C'),
('DIU','VADU','Diu Airport','Diu','Dadra & NH','WEST','India','IN',20.7131,70.921,'Asia/Kolkata',31,TRUE,FALSE,TRUE,1,1,1400,'D'),
('BHO','VABP','Raja Bhoj Airport','Bhopal','Madhya Pradesh','CENTRAL','India','IN',23.2875,77.3374,'Asia/Kolkata',1711,TRUE,FALSE,TRUE,1,1,2750,'B'),
('IDR','VAID','Devi Ahilyabai Holkar Airport','Indore','Madhya Pradesh','CENTRAL','India','IN',22.7218,75.8011,'Asia/Kolkata',1850,TRUE,FALSE,TRUE,1,1,2750,'B'),
('JLR','VAJB','Jabalpur Airport','Jabalpur','Madhya Pradesh','CENTRAL','India','IN',23.1778,80.052,'Asia/Kolkata',1624,TRUE,FALSE,TRUE,1,1,2438,'C'),
('KHI','VAKJ','Khajuraho Airport','Khajuraho','Madhya Pradesh','CENTRAL','India','IN',24.8172,79.9186,'Asia/Kolkata',728,TRUE,FALSE,TRUE,1,1,1981,'D'),
('RPR','VARP','Swami Vivekananda Airport','Raipur','Chhattisgarh','CENTRAL','India','IN',21.1804,81.7388,'Asia/Kolkata',1041,TRUE,FALSE,TRUE,1,1,2743,'B'),
('JRG','VEJH','Jharsuguda Airport','Jharsuguda','Odisha','CENTRAL','India','IN',21.9135,84.0504,'Asia/Kolkata',751,TRUE,FALSE,TRUE,1,1,2285,'C'),
('JAG','VAJG','Jagdalpur Airport','Jagdalpur','Chhattisgarh','CENTRAL','India','IN',19.0742,82.0319,'Asia/Kolkata',1862,TRUE,FALSE,TRUE,1,1,1981,'E'),
('CCU','VECC','Netaji Subhas Chandra Bose International Airport','Kolkata','West Bengal','EAST','India','IN',22.652,88.4463,'Asia/Kolkata',19,TRUE,TRUE,TRUE,2,2,3627,'A'),
('IXB','VEBD','Bagdogra Airport','Siliguri','West Bengal','EAST','India','IN',26.6812,88.3286,'Asia/Kolkata',412,TRUE,FALSE,TRUE,1,1,3050,'B'),
('BBI','VEBS','Biju Patnaik International Airport','Bhubaneswar','Odisha','EAST','India','IN',20.2444,85.8178,'Asia/Kolkata',148,TRUE,TRUE,TRUE,1,1,2743,'B'),
('IXR','VERC','Birsa Munda Airport','Ranchi','Jharkhand','EAST','India','IN',23.3143,85.3217,'Asia/Kolkata',2148,TRUE,FALSE,TRUE,1,1,2397,'B'),
('PAT','VEPT','Jay Prakash Narayan International Airport','Patna','Bihar','EAST','India','IN',25.5913,85.088,'Asia/Kolkata',170,TRUE,FALSE,TRUE,1,1,2130,'B'),
('GAY','VEGY','Gaya Airport','Gaya','Bihar','EAST','India','IN',24.7444,84.9512,'Asia/Kolkata',380,TRUE,FALSE,TRUE,1,1,2286,'C'),
('DBR','VEDB','Deoghar Airport','Deoghar','Jharkhand','EAST','India','IN',24.4622,86.7086,'Asia/Kolkata',830,TRUE,FALSE,TRUE,1,1,3600,'D'),
('PKR','VEPG','Pakyong Airport','Gangtok','Sikkim','EAST','India','IN',27.2257,88.5849,'Asia/Kolkata',4593,TRUE,FALSE,TRUE,1,1,1750,'D'),
('GAU','VEGT','Lokpriya Gopinath Bordoloi International Airport','Guwahati','Assam','NORTHEAST','India','IN',26.1061,91.5859,'Asia/Kolkata',162,TRUE,TRUE,TRUE,1,1,2900,'A'),
('DIB','VEMN','Dibrugarh Airport','Dibrugarh','Assam','NORTHEAST','India','IN',27.4839,95.0169,'Asia/Kolkata',362,TRUE,FALSE,TRUE,1,1,2286,'C'),
('IXI','VELP','Lilabari Airport','Lakhimpur','Assam','NORTHEAST','India','IN',27.2955,94.0976,'Asia/Kolkata',330,TRUE,FALSE,TRUE,1,1,2040,'D'),
('IXS','VEKU','Silchar Airport','Silchar','Assam','NORTHEAST','India','IN',24.9129,92.9787,'Asia/Kolkata',352,TRUE,FALSE,TRUE,1,1,2285,'C'),
('TEZ','VETZ','Tezpur Airport','Tezpur','Assam','NORTHEAST','India','IN',26.7091,92.7847,'Asia/Kolkata',240,TRUE,FALSE,TRUE,1,1,2286,'D'),
('JRH','VEJT','Jorhat Airport','Jorhat','Assam','NORTHEAST','India','IN',26.7315,94.1755,'Asia/Kolkata',369,TRUE,FALSE,TRUE,1,1,2744,'C'),
('IMF','VEIM','Imphal International Airport','Imphal','Manipur','NORTHEAST','India','IN',24.76,93.8967,'Asia/Kolkata',2539,TRUE,TRUE,TRUE,1,1,2743,'B'),
('DMU','VEMR','Dimapur Airport','Dimapur','Nagaland','NORTHEAST','India','IN',25.8839,93.7712,'Asia/Kolkata',487,TRUE,FALSE,TRUE,1,1,2440,'C'),
('AJL','VEAZ','Lengpui Airport','Aizawl','Mizoram','NORTHEAST','India','IN',23.8405,92.6197,'Asia/Kolkata',1629,TRUE,FALSE,TRUE,1,1,2480,'C'),
('SHL','VESL','Shillong Airport','Shillong','Meghalaya','NORTHEAST','India','IN',25.7036,91.9787,'Asia/Kolkata',2910,TRUE,FALSE,TRUE,1,1,1830,'D'),
('IXA','VEAT','Agartala Airport','Agartala','Tripura','NORTHEAST','India','IN',23.887,91.2404,'Asia/Kolkata',46,TRUE,FALSE,TRUE,1,1,2286,'C'),
('HGI','VEPH','Pasighat Airport','Pasighat','Arunachal Pradesh','NORTHEAST','India','IN',28.0661,95.3356,'Asia/Kolkata',477,TRUE,FALSE,TRUE,1,1,1981,'D'),
('BLR','VOBL','Kempegowda International Airport','Bengaluru','Karnataka','SOUTH','India','IN',13.1986,77.7066,'Asia/Kolkata',3000,TRUE,TRUE,TRUE,2,2,4000,'A'),
('MAA','VOMM','Chennai International Airport','Chennai','Tamil Nadu','SOUTH','India','IN',12.99,80.1693,'Asia/Kolkata',52,TRUE,TRUE,TRUE,4,2,3600,'A'),
('HYD','VOHS','Rajiv Gandhi International Airport','Hyderabad','Telangana','SOUTH','India','IN',17.2313,78.4298,'Asia/Kolkata',2024,TRUE,TRUE,TRUE,1,2,4260,'A'),
('TRV','VOTV','Trivandrum International Airport','Thiruvananthapuram','Kerala','SOUTH','India','IN',8.4782,76.9201,'Asia/Kolkata',15,TRUE,TRUE,TRUE,1,1,3400,'B'),
('COK','VOCI','Cochin International Airport','Kochi','Kerala','SOUTH','India','IN',10.152,76.4019,'Asia/Kolkata',30,TRUE,TRUE,TRUE,2,1,3400,'A'),
('CCJ','VOCL','Calicut International Airport','Kozhikode','Kerala','SOUTH','India','IN',11.1368,75.9553,'Asia/Kolkata',334,TRUE,TRUE,TRUE,1,1,3050,'B'),
('CNN','VOKT','Kannur International Airport','Kannur','Kerala','SOUTH','India','IN',11.9186,75.5472,'Asia/Kolkata',328,TRUE,TRUE,TRUE,1,1,3050,'B'),
('IXM','VOMD','Madurai Airport','Madurai','Tamil Nadu','SOUTH','India','IN',9.8345,78.0934,'Asia/Kolkata',459,TRUE,FALSE,TRUE,1,1,2900,'B'),
('TRZ','VOTR','Tiruchirappalli International Airport','Tiruchirappalli','Tamil Nadu','SOUTH','India','IN',10.7654,78.7097,'Asia/Kolkata',88,TRUE,TRUE,TRUE,1,1,2895,'B'),
('CJB','VOCB','Coimbatore International Airport','Coimbatore','Tamil Nadu','SOUTH','India','IN',11.03,77.0434,'Asia/Kolkata',1324,TRUE,TRUE,TRUE,1,1,2990,'B'),
('TIR','VOTP','Tirupati Airport','Tirupati','Andhra Pradesh','SOUTH','India','IN',13.6325,79.5433,'Asia/Kolkata',350,TRUE,FALSE,TRUE,1,1,2380,'C'),
('VTZ','VEVZ','Visakhapatnam Airport','Visakhapatnam','Andhra Pradesh','SOUTH','India','IN',17.7212,83.2245,'Asia/Kolkata',15,TRUE,TRUE,TRUE,1,1,3200,'B'),
('VGA','VOVR','Vijayawada Airport','Vijayawada','Andhra Pradesh','SOUTH','India','IN',16.5304,80.7968,'Asia/Kolkata',82,TRUE,FALSE,TRUE,1,1,3000,'B'),
('RJA','VORY','Rajahmundry Airport','Rajahmundry','Andhra Pradesh','SOUTH','India','IN',17.1103,81.8182,'Asia/Kolkata',151,TRUE,FALSE,TRUE,1,1,2400,'C'),
('IXE','VOMN','Mangalore International Airport','Mangalore','Karnataka','SOUTH','India','IN',12.9613,74.8904,'Asia/Kolkata',337,TRUE,TRUE,TRUE,1,1,2851,'B'),
('HBX','VOHB','Hubli Airport','Hubballi','Karnataka','SOUTH','India','IN',15.3617,75.0849,'Asia/Kolkata',2171,TRUE,FALSE,TRUE,1,1,2286,'C'),
('MYQ','VOYK','Mysore Airport','Mysuru','Karnataka','SOUTH','India','IN',12.2308,76.6496,'Asia/Kolkata',2469,TRUE,FALSE,TRUE,1,1,1745,'C'),
('BJP','VOBG','Bellary Airport','Ballari','Karnataka','SOUTH','India','IN',15.1628,76.8828,'Asia/Kolkata',1696,TRUE,FALSE,TRUE,1,1,2000,'D'),
('WGC','VOWA','Warangal Airport','Warangal','Telangana','SOUTH','India','IN',17.9144,79.602,'Asia/Kolkata',935,TRUE,FALSE,TRUE,1,1,2285,'D'),
('IXZ','VOPB','Veer Savarkar International Airport','Port Blair','Andaman & Nicobar','ISLAND','India','IN',11.6412,92.7297,'Asia/Kolkata',14,TRUE,FALSE,TRUE,1,1,3290,'B'),
('AGX','VOAT','Agatti Airport','Agatti Island','Lakshadweep','ISLAND','India','IN',10.8237,72.176,'Asia/Kolkata',14,TRUE,FALSE,TRUE,1,1,1204,'D'),
('DXB','OMDB','Dubai International Airport','Dubai','Dubai','INT','UAE','AE',25.2532,55.3657,'Asia/Dubai',62,FALSE,TRUE,TRUE,3,3,4000,'A'),
('SIN','WSSS','Changi Airport','Singapore','Singapore','INT','Singapore','SG',1.3644,103.9915,'Asia/Singapore',22,FALSE,TRUE,TRUE,4,2,4000,'A'),
('LHR','EGLL','Heathrow Airport','London','England','INT','UK','GB',51.47,-0.4543,'Europe/London',83,FALSE,TRUE,TRUE,5,2,3902,'A'),
('DOH','OTHH','Hamad International Airport','Doha','Qatar','INT','Qatar','QA',25.2731,51.608,'Asia/Qatar',13,FALSE,TRUE,TRUE,1,2,4850,'A'),
('AUH','OMAA','Abu Dhabi International Airport','Abu Dhabi','UAE','INT','UAE','AE',24.433,54.6511,'Asia/Dubai',88,FALSE,TRUE,TRUE,3,2,4100,'A'),
('BKK','VTBS','Suvarnabhumi Airport','Bangkok','Bangkok','INT','Thailand','TH',13.69,100.7501,'Asia/Bangkok',5,FALSE,TRUE,TRUE,2,2,4000,'A'),
('KUL','WMKK','Kuala Lumpur International Airport','Kuala Lumpur','Selangor','INT','Malaysia','MY',2.7456,101.7099,'Asia/Kuala_Lumpur',69,FALSE,TRUE,TRUE,2,2,4019,'A'),
('JFK','KJFK','John F. Kennedy International Airport','New York','New York','INT','USA','US',40.6413,-73.7781,'America/New_York',13,FALSE,TRUE,TRUE,6,4,4423,'A');

-- ================================================================
-- STEP 3: AIRLINES
-- ================================================================
CREATE TABLE public.airlines (
  iata_code     TEXT PRIMARY KEY,
  icao_code     TEXT UNIQUE,
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

INSERT INTO public.airlines (iata_code,icao_code,name,short_name,country,is_domestic,is_lowcost,hub_airport,website,contact_phone) VALUES
('AI','AIC','Air India','Air India','India',TRUE,FALSE,'DEL','https://airindia.com','+91-11-24622220'),
('6E','IGO','IndiGo','IndiGo','India',TRUE,TRUE,'DEL','https://goindigo.in','+91-99-10383838'),
('SG','SEJ','SpiceJet','SpiceJet','India',TRUE,TRUE,'DEL','https://spicejet.com','+91-98-71803333'),
('UK','TAI','Vistara','Vistara','India',TRUE,FALSE,'DEL','https://airvistara.com','+91-92-89228922'),
('IX','MDV','Air India Express','AIX','India',TRUE,TRUE,'COK','https://airindiaexpress.in','+91-95-55888840'),
('QP','AQP','Akasa Air','Akasa','India',TRUE,TRUE,'BOM','https://akasaair.com','+91-86-52001000'),
('S5','SNJ','Star Air','Star Air','India',TRUE,FALSE,'BLR','https://starair.in','+91-86-50009000'),
('2T','TLB','TruJet','TruJet','India',TRUE,FALSE,'HYD','https://trujet.com','+91-40-44334433'),
('EK','UAE','Emirates','Emirates','UAE',FALSE,FALSE,'DXB','https://emirates.com','+971-600555555'),
('SQ','SIA','Singapore Airlines','SIA','Singapore',FALSE,FALSE,'SIN','https://singaporeair.com','+65-62238888'),
('QR','QTR','Qatar Airways','Qatar Airways','Qatar',FALSE,FALSE,'DOH','https://qatarairways.com','+974-40221111'),
('EY','ETD','Etihad Airways','Etihad','UAE',FALSE,FALSE,'AUH','https://etihad.com','+971-600555666'),
('BA','BAW','British Airways','British Airways','UK',FALSE,FALSE,'LHR','https://britishairways.com','+44-3444930787');

-- ================================================================
-- STEP 4: PROFILES (no auth.users FK to avoid editor issues)
-- ================================================================
CREATE TABLE public.profiles (
  id                  UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  auth_user_id        UUID UNIQUE,
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
  aadhaar_last4       TEXT,
  preferred_currency  TEXT DEFAULT 'INR',
  preferred_cabin     TEXT DEFAULT 'ECONOMY',
  preferred_language  TEXT DEFAULT 'en',
  avatar_url          TEXT,
  notify_email        BOOLEAN DEFAULT TRUE,
  notify_sms          BOOLEAN DEFAULT TRUE,
  notify_whatsapp     BOOLEAN DEFAULT FALSE,
  notify_push         BOOLEAN DEFAULT FALSE,
  preferred_airlines  TEXT[],
  preferred_seat      TEXT DEFAULT 'WINDOW',
  meal_preference     TEXT DEFAULT 'VEG',
  frequent_flyer      JSONB DEFAULT '{}',
  skymind_points      INT DEFAULT 0,
  tier                TEXT DEFAULT 'BLUE',
  total_bookings      INT DEFAULT 0,
  total_spent         DECIMAL(12,2) DEFAULT 0,
  last_login          TIMESTAMPTZ,
  login_count         INT DEFAULT 0,
  is_active           BOOLEAN DEFAULT TRUE,
  created_at          TIMESTAMPTZ DEFAULT NOW(),
  updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_profiles_email       ON public.profiles(email);
CREATE INDEX idx_profiles_auth_user   ON public.profiles(auth_user_id);
CREATE INDEX idx_profiles_phone       ON public.profiles(phone);

-- ================================================================
-- STEP 5: USER SESSIONS
-- ================================================================
CREATE TABLE public.user_sessions (
  id           UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  user_id      UUID REFERENCES public.profiles(id) ON DELETE CASCADE,
  ip_address   INET,
  user_agent   TEXT,
  device_type  TEXT,
  city         TEXT,
  country      TEXT,
  is_active    BOOLEAN DEFAULT TRUE,
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  last_seen_at TIMESTAMPTZ DEFAULT NOW(),
  expires_at   TIMESTAMPTZ
);

CREATE INDEX idx_sessions_user ON public.user_sessions(user_id);

-- ================================================================
-- STEP 6: OTP VERIFICATIONS
-- ================================================================
CREATE TABLE public.otp_verifications (
  id          UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  user_id     UUID REFERENCES public.profiles(id) ON DELETE CASCADE,
  identifier  TEXT NOT NULL,
  otp_hash    TEXT NOT NULL,
  purpose     TEXT NOT NULL DEFAULT 'PHONE_VERIFY',
  channel     TEXT NOT NULL DEFAULT 'SMS',
  is_used     BOOLEAN DEFAULT FALSE,
  attempts    INT DEFAULT 0,
  max_attempts INT DEFAULT 5,
  expires_at  TIMESTAMPTZ NOT NULL,
  used_at     TIMESTAMPTZ,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_otp_user       ON public.otp_verifications(user_id);
CREATE INDEX idx_otp_identifier ON public.otp_verifications(identifier);

-- ================================================================
-- STEP 7: ROUTES
-- ================================================================
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
  is_popular       BOOLEAN DEFAULT FALSE,
  created_at       TIMESTAMPTZ DEFAULT NOW(),
  updated_at       TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(origin_code, destination_code)
);

CREATE INDEX idx_routes_origin ON public.routes(origin_code);
CREATE INDEX idx_routes_dest   ON public.routes(destination_code);

-- ================================================================
-- STEP 8: FLIGHTS (live/cached)
-- ================================================================
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
  base_price       DECIMAL(10,2),
  current_price    DECIMAL(10,2),
  currency         TEXT DEFAULT 'INR',
  status           TEXT DEFAULT 'SCHEDULED',
  terminal         TEXT,
  gate             TEXT,
  baggage_kg       INT DEFAULT 15,
  amadeus_offer_id TEXT,
  raw_offer        JSONB,
  created_at       TIMESTAMPTZ DEFAULT NOW(),
  updated_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_flights_route     ON public.flights(origin_code, destination_code);
CREATE INDEX idx_flights_departure ON public.flights(departure_time);
CREATE INDEX idx_flights_airline   ON public.flights(airline_code);
CREATE INDEX idx_flights_status    ON public.flights(status);

-- ================================================================
-- STEP 9: PRICE HISTORY (ML training data)
-- ================================================================
CREATE TABLE public.price_history (
  id               UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  origin_code      TEXT REFERENCES public.airports(iata_code),
  destination_code TEXT REFERENCES public.airports(iata_code),
  airline_code     TEXT REFERENCES public.airlines(iata_code),
  flight_number    TEXT,
  cabin_class      TEXT DEFAULT 'ECONOMY',
  price            DECIMAL(10,2) NOT NULL,
  currency         TEXT DEFAULT 'INR',
  departure_date   DATE NOT NULL,
  days_until_dep   INT,
  day_of_week      INT,
  month            INT,
  week_of_year     INT,
  is_holiday       BOOLEAN DEFAULT FALSE,
  is_weekend       BOOLEAN DEFAULT FALSE,
  seats_available  INT,
  recorded_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ph_route ON public.price_history(origin_code, destination_code);
CREATE INDEX idx_ph_date  ON public.price_history(departure_date);
CREATE INDEX idx_ph_price ON public.price_history(price);

-- ================================================================
-- STEP 10: COUPONS
-- ================================================================
CREATE TABLE public.coupons (
  id              UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  code            TEXT UNIQUE NOT NULL,
  description     TEXT,
  discount_type   TEXT NOT NULL DEFAULT 'PERCENT',
  discount_value  DECIMAL(10,2) NOT NULL,
  max_discount    DECIMAL(10,2),
  min_booking_amt DECIMAL(10,2) DEFAULT 0,
  usage_limit     INT,
  used_count      INT DEFAULT 0,
  per_user_limit  INT DEFAULT 1,
  applicable_for  TEXT DEFAULT 'ALL',
  valid_from      TIMESTAMPTZ DEFAULT NOW(),
  valid_until     TIMESTAMPTZ,
  is_active       BOOLEAN DEFAULT TRUE,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO public.coupons (code,description,discount_type,discount_value,max_discount,min_booking_amt,usage_limit,per_user_limit,valid_until) VALUES
('SKYMIND10','10% off on all bookings','PERCENT',10,1500,3000,1000,1,NOW()+INTERVAL '1 year'),
('FLAT500','Flat Rs.500 off','FLAT',500,500,2000,500,1,NOW()+INTERVAL '6 months'),
('NEWUSER','15% off for new users','PERCENT',15,2000,1000,999,1,NOW()+INTERVAL '1 year'),
('MONSOON40','40% off monsoon sale','PERCENT',40,3000,2500,200,1,NOW()+INTERVAL '3 months'),
('WEEKEND20','20% off weekend flights','PERCENT',20,2500,1500,300,2,NOW()+INTERVAL '6 months');

-- ================================================================
-- STEP 11: BOOKINGS
-- ================================================================
CREATE TABLE public.bookings (
  id                    UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  booking_reference     TEXT UNIQUE NOT NULL,
  user_id               UUID REFERENCES public.profiles(id),
  flight_id             UUID REFERENCES public.flights(id),
  amadeus_booking_id    TEXT,
  pnr                   TEXT,
  status                TEXT DEFAULT 'PENDING',
  payment_status        TEXT DEFAULT 'UNPAID',
  total_price           DECIMAL(10,2) NOT NULL,
  base_fare             DECIMAL(10,2),
  taxes                 DECIMAL(10,2),
  baggage_charges       DECIMAL(10,2) DEFAULT 0,
  meal_charges          DECIMAL(10,2) DEFAULT 0,
  seat_charges          DECIMAL(10,2) DEFAULT 0,
  discount_amount       DECIMAL(10,2) DEFAULT 0,
  currency              TEXT DEFAULT 'INR',
  cabin_class           TEXT DEFAULT 'ECONOMY',
  num_passengers        INT DEFAULT 1,
  contact_email         TEXT,
  contact_phone         TEXT,
  coupon_code           TEXT REFERENCES public.coupons(code),
  payment_method        TEXT,
  payment_id            TEXT,
  razorpay_order_id     TEXT,
  razorpay_signature    TEXT,
  skymind_points_used   INT DEFAULT 0,
  skymind_points_earned INT DEFAULT 0,
  booking_source        TEXT DEFAULT 'WEB',
  flight_offer_data     JSONB,
  confirmation_sent     BOOLEAN DEFAULT FALSE,
  reminder_sent         BOOLEAN DEFAULT FALSE,
  checkin_notif_sent    BOOLEAN DEFAULT FALSE,
  status_notif_sent     BOOLEAN DEFAULT FALSE,
  cancelled_at          TIMESTAMPTZ,
  cancellation_reason   TEXT,
  refund_amount         DECIMAL(10,2),
  refund_id             TEXT,
  refund_status         TEXT,
  created_at            TIMESTAMPTZ DEFAULT NOW(),
  updated_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_bookings_user      ON public.bookings(user_id);
CREATE INDEX idx_bookings_ref       ON public.bookings(booking_reference);
CREATE INDEX idx_bookings_status    ON public.bookings(status);
CREATE INDEX idx_bookings_payment   ON public.bookings(payment_status);
CREATE INDEX idx_bookings_departure ON public.bookings(created_at);

-- ================================================================
-- STEP 12: PASSENGERS
-- ================================================================
CREATE TABLE public.passengers (
  id               UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  booking_id       UUID NOT NULL REFERENCES public.bookings(id) ON DELETE CASCADE,
  passenger_type   TEXT DEFAULT 'ADULT',
  title            TEXT,
  first_name       TEXT NOT NULL,
  last_name        TEXT NOT NULL,
  date_of_birth    DATE,
  gender           TEXT,
  nationality      TEXT DEFAULT 'Indian',
  passport_number  TEXT,
  passport_expiry  DATE,
  passport_country TEXT DEFAULT 'India',
  aadhaar_number   TEXT,
  seat_number      TEXT,
  seat_preference  TEXT DEFAULT 'WINDOW',
  meal_preference  TEXT DEFAULT 'VEG',
  baggage_kg       INT DEFAULT 15,
  ff_number        TEXT,
  ff_airline       TEXT,
  special_request  TEXT,
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_passengers_booking ON public.passengers(booking_id);

-- ================================================================
-- STEP 13: NOTIFICATIONS
-- ================================================================
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
  max_retries   INT DEFAULT 3,
  scheduled_at  TIMESTAMPTZ DEFAULT NOW(),
  sent_at       TIMESTAMPTZ,
  delivered_at  TIMESTAMPTZ,
  opened_at     TIMESTAMPTZ,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_notif_user      ON public.notifications(user_id);
CREATE INDEX idx_notif_status    ON public.notifications(status);
CREATE INDEX idx_notif_scheduled ON public.notifications(scheduled_at);
CREATE INDEX idx_notif_type      ON public.notifications(type);

-- ================================================================
-- STEP 14: PRICE ALERTS
-- ================================================================
CREATE TABLE public.price_alerts (
  id               UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  user_id          UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  origin_code      TEXT NOT NULL REFERENCES public.airports(iata_code),
  destination_code TEXT NOT NULL REFERENCES public.airports(iata_code),
  departure_date   DATE NOT NULL,
  return_date      DATE,
  cabin_class      TEXT DEFAULT 'ECONOMY',
  adults           INT DEFAULT 1,
  children         INT DEFAULT 0,
  target_price     DECIMAL(10,2) NOT NULL,
  currency         TEXT DEFAULT 'INR',
  preferred_airline TEXT REFERENCES public.airlines(iata_code),
  is_active        BOOLEAN DEFAULT TRUE,
  notify_email     BOOLEAN DEFAULT TRUE,
  notify_sms       BOOLEAN DEFAULT TRUE,
  notify_whatsapp  BOOLEAN DEFAULT FALSE,
  last_checked     TIMESTAMPTZ,
  last_price       DECIMAL(10,2),
  lowest_seen      DECIMAL(10,2),
  triggered_count  INT DEFAULT 0,
  triggered_at     TIMESTAMPTZ,
  expires_at       TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '90 days'),
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_alerts_user   ON public.price_alerts(user_id);
CREATE INDEX idx_alerts_route  ON public.price_alerts(origin_code, destination_code);
CREATE INDEX idx_alerts_active ON public.price_alerts(is_active) WHERE is_active = TRUE;
CREATE INDEX idx_alerts_date   ON public.price_alerts(departure_date);

-- ================================================================
-- STEP 15: SAVED SEARCHES
-- ================================================================
CREATE TABLE public.saved_searches (
  id               UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  user_id          UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  search_name      TEXT,
  origin_code      TEXT REFERENCES public.airports(iata_code),
  destination_code TEXT REFERENCES public.airports(iata_code),
  departure_date   DATE,
  return_date      DATE,
  adults           INT DEFAULT 1,
  children         INT DEFAULT 0,
  infants          INT DEFAULT 0,
  cabin_class      TEXT DEFAULT 'ECONOMY',
  is_round_trip    BOOLEAN DEFAULT FALSE,
  search_params    JSONB,
  search_count     INT DEFAULT 1,
  last_searched    TIMESTAMPTZ DEFAULT NOW(),
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_searches_user ON public.saved_searches(user_id);

-- ================================================================
-- STEP 16: ROW LEVEL SECURITY
-- ================================================================
ALTER TABLE public.airports          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.airlines          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.routes            ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.flights           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.price_history     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coupons           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profiles          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_sessions     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.otp_verifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.bookings          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.passengers        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.price_alerts      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.saved_searches    ENABLE ROW LEVEL SECURITY;

-- Public read (no auth needed)
CREATE POLICY "pub_airports"  ON public.airports      FOR SELECT USING (TRUE);
CREATE POLICY "pub_airlines"  ON public.airlines      FOR SELECT USING (TRUE);
CREATE POLICY "pub_routes"    ON public.routes        FOR SELECT USING (TRUE);
CREATE POLICY "pub_flights"   ON public.flights       FOR SELECT USING (TRUE);
CREATE POLICY "pub_ph"        ON public.price_history FOR SELECT USING (TRUE);
CREATE POLICY "pub_coupons"   ON public.coupons       FOR SELECT USING (is_active = TRUE);

-- Profiles
CREATE POLICY "own_profile_select" ON public.profiles FOR SELECT USING (auth.uid() = auth_user_id);
CREATE POLICY "own_profile_insert" ON public.profiles FOR INSERT WITH CHECK (auth.uid() = auth_user_id);
CREATE POLICY "own_profile_update" ON public.profiles FOR UPDATE USING (auth.uid() = auth_user_id);

-- Sessions
CREATE POLICY "own_sessions" ON public.user_sessions FOR ALL USING
  (user_id IN (SELECT id FROM public.profiles WHERE auth_user_id = auth.uid()));

-- OTP
CREATE POLICY "own_otp" ON public.otp_verifications FOR ALL USING
  (user_id IN (SELECT id FROM public.profiles WHERE auth_user_id = auth.uid()));

-- Bookings
CREATE POLICY "own_bookings_select" ON public.bookings FOR SELECT USING
  (user_id IN (SELECT id FROM public.profiles WHERE auth_user_id = auth.uid()));
CREATE POLICY "own_bookings_insert" ON public.bookings FOR INSERT WITH CHECK
  (user_id IN (SELECT id FROM public.profiles WHERE auth_user_id = auth.uid()));
CREATE POLICY "own_bookings_update" ON public.bookings FOR UPDATE USING
  (user_id IN (SELECT id FROM public.profiles WHERE auth_user_id = auth.uid()));

-- Passengers
CREATE POLICY "own_passengers_select" ON public.passengers FOR SELECT USING
  (booking_id IN (SELECT id FROM public.bookings WHERE user_id IN
    (SELECT id FROM public.profiles WHERE auth_user_id = auth.uid())));
CREATE POLICY "own_passengers_insert" ON public.passengers FOR INSERT WITH CHECK
  (booking_id IN (SELECT id FROM public.bookings WHERE user_id IN
    (SELECT id FROM public.profiles WHERE auth_user_id = auth.uid())));

-- Notifications
CREATE POLICY "own_notifications" ON public.notifications FOR SELECT USING
  (user_id IN (SELECT id FROM public.profiles WHERE auth_user_id = auth.uid()));

-- Price Alerts
CREATE POLICY "own_alerts" ON public.price_alerts FOR ALL USING
  (user_id IN (SELECT id FROM public.profiles WHERE auth_user_id = auth.uid()));

-- Saved Searches
CREATE POLICY "own_searches" ON public.saved_searches FOR ALL USING
  (user_id IN (SELECT id FROM public.profiles WHERE auth_user_id = auth.uid()));

-- ================================================================
-- STEP 17: FUNCTIONS
-- ================================================================

-- Generate unique booking reference (SKY + year + 6 random chars)
CREATE OR REPLACE FUNCTION public.gen_booking_ref()
RETURNS TEXT LANGUAGE plpgsql AS $$
DECLARE
  ref TEXT;
  exists_already BOOLEAN;
BEGIN
  LOOP
    ref := 'SKY' || TO_CHAR(NOW(), 'YY') ||
           UPPER(SUBSTRING(MD5(RANDOM()::TEXT) FROM 1 FOR 6));
    SELECT EXISTS(SELECT 1 FROM public.bookings WHERE booking_reference = ref)
    INTO exists_already;
    EXIT WHEN NOT exists_already;
  END LOOP;
  RETURN ref;
END;
$$;

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION public.update_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_profiles_updated  BEFORE UPDATE ON public.profiles
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
CREATE TRIGGER trg_bookings_updated  BEFORE UPDATE ON public.bookings
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
CREATE TRIGGER trg_flights_updated   BEFORE UPDATE ON public.flights
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
CREATE TRIGGER trg_routes_updated    BEFORE UPDATE ON public.routes
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

-- Auto-fill booking_reference before insert
CREATE OR REPLACE FUNCTION public.fill_booking_ref()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.booking_reference IS NULL OR NEW.booking_reference = '' THEN
    NEW.booking_reference := public.gen_booking_ref();
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_booking_ref BEFORE INSERT ON public.bookings
  FOR EACH ROW EXECUTE FUNCTION public.fill_booking_ref();

-- Handle payment confirmed: queue notifications + award points
CREATE OR REPLACE FUNCTION public.handle_booking_confirmed()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
  v_profile public.profiles%ROWTYPE;
  v_points  INT;
BEGIN
  IF NEW.payment_status = 'PAID' AND (OLD.payment_status IS DISTINCT FROM 'PAID') THEN
    SELECT * INTO v_profile FROM public.profiles WHERE id = NEW.user_id;

    -- Queue email notification
    IF v_profile.notify_email = TRUE AND NEW.contact_email IS NOT NULL THEN
      INSERT INTO public.notifications
        (user_id, booking_id, type, channel, recipient, subject, message, template_id)
      VALUES
        (NEW.user_id, NEW.id, 'BOOKING_CONFIRMATION', 'EMAIL', NEW.contact_email,
         'Booking ' || NEW.booking_reference || ' Confirmed!',
         'Your SkyMind booking is confirmed. Amount: Rs.' || NEW.total_price,
         'booking_confirm_email');
    END IF;

    -- Queue SMS notification
    IF v_profile.notify_sms = TRUE AND NEW.contact_phone IS NOT NULL THEN
      INSERT INTO public.notifications
        (user_id, booking_id, type, channel, recipient, message, template_id)
      VALUES
        (NEW.user_id, NEW.id, 'BOOKING_CONFIRMATION', 'SMS', NEW.contact_phone,
         'SkyMind: Bkg ' || NEW.booking_reference || ' confirmed! Rs.' || NEW.total_price || ' -SKYMND',
         'booking_confirm_sms');
    END IF;

    -- Award loyalty points (1 point per Rs.100)
    v_points := GREATEST(0, FLOOR(NEW.total_price / 100)::INT);
    NEW.skymind_points_earned := v_points;
    NEW.status := 'CONFIRMED';
    NEW.confirmation_sent := TRUE;

    UPDATE public.profiles SET
      skymind_points = skymind_points + v_points,
      total_bookings = total_bookings + 1,
      total_spent    = total_spent + NEW.total_price,
      tier = CASE
        WHEN total_spent + NEW.total_price >= 500000 THEN 'PLATINUM'
        WHEN total_spent + NEW.total_price >= 150000 THEN 'GOLD'
        WHEN total_spent + NEW.total_price >= 50000  THEN 'SILVER'
        ELSE 'BLUE'
      END
    WHERE id = NEW.user_id;
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_booking_confirmed
  BEFORE UPDATE ON public.bookings
  FOR EACH ROW EXECUTE FUNCTION public.handle_booking_confirmed();

-- Handle new Supabase auth signup → create profile + queue welcome email
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
  v_profile_id UUID;
  v_name TEXT;
BEGIN
  v_name := COALESCE(
    NEW.raw_user_meta_data->>'full_name',
    NEW.raw_user_meta_data->>'name',
    SPLIT_PART(NEW.email, '@', 1)
  );

  INSERT INTO public.profiles (auth_user_id, email, full_name, display_name, email_verified)
  VALUES (NEW.id, NEW.email, v_name, v_name, (NEW.email_confirmed_at IS NOT NULL))
  ON CONFLICT (email) DO UPDATE SET
    auth_user_id   = EXCLUDED.auth_user_id,
    email_verified = EXCLUDED.email_verified
  RETURNING id INTO v_profile_id;

  -- Queue welcome email
  INSERT INTO public.notifications
    (user_id, type, channel, recipient, subject, message, template_id)
  VALUES
    (v_profile_id, 'WELCOME', 'EMAIL', NEW.email,
     'Welcome to SkyMind!',
     'Hi ' || v_name || '! Your AI-powered flight companion is ready.',
     'welcome_email');

  RETURN NEW;
END;
$$;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Expire old price alerts
CREATE OR REPLACE FUNCTION public.expire_old_alerts()
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  UPDATE public.price_alerts
  SET is_active = FALSE
  WHERE is_active = TRUE
    AND (expires_at < NOW() OR departure_date < CURRENT_DATE);
END;
$$;

-- ================================================================
-- STEP 18: VIEWS
-- ================================================================

-- Booking details with user info
CREATE VIEW public.v_booking_details AS
SELECT
  b.id,
  b.booking_reference,
  b.pnr,
  b.status,
  b.payment_status,
  b.total_price,
  b.base_fare,
  b.taxes,
  b.discount_amount,
  b.currency,
  b.cabin_class,
  b.num_passengers,
  b.contact_email,
  b.contact_phone,
  b.checkin_notif_sent,
  b.confirmation_sent,
  b.flight_offer_data,
  b.created_at,
  b.cancelled_at,
  b.refund_amount,
  b.refund_status,
  p.full_name    AS user_name,
  p.email        AS user_email,
  p.phone        AS user_phone,
  p.notify_email,
  p.notify_sms,
  p.notify_whatsapp,
  p.skymind_points,
  p.tier
FROM public.bookings b
JOIN public.profiles p ON b.user_id = p.id;

-- Pending notifications queue (for scheduler)
CREATE VIEW public.v_pending_notifications AS
SELECT *
FROM public.notifications
WHERE status = 'PENDING'
  AND scheduled_at <= NOW()
  AND retry_count < max_retries
ORDER BY scheduled_at ASC
LIMIT 200;

-- Active price alerts with user + airport info
CREATE VIEW public.v_active_alerts AS
SELECT
  pa.id,
  pa.user_id,
  pa.origin_code,
  pa.destination_code,
  pa.departure_date,
  pa.cabin_class,
  pa.target_price,
  pa.notify_email,
  pa.notify_sms,
  pa.notify_whatsapp,
  pa.last_checked,
  pa.last_price,
  pa.lowest_seen,
  pa.triggered_count,
  pa.expires_at,
  p.full_name,
  p.email,
  p.phone,
  ao.city AS origin_city,
  ao.name AS origin_airport,
  ad.city AS dest_city,
  ad.name AS dest_airport
FROM public.price_alerts pa
JOIN public.profiles p  ON pa.user_id          = p.id
JOIN public.airports ao ON pa.origin_code      = ao.iata_code
JOIN public.airports ad ON pa.destination_code = ad.iata_code
WHERE pa.is_active = TRUE
  AND (pa.expires_at IS NULL OR pa.expires_at > NOW())
  AND pa.departure_date >= CURRENT_DATE;

-- Domestic routes with full airport details
CREATE VIEW public.v_domestic_routes AS
SELECT
  r.id,
  r.origin_code,
  ao.city         AS origin_city,
  ao.name         AS origin_airport,
  ao.state        AS origin_state,
  ao.region       AS origin_region,
  ao.latitude     AS origin_lat,
  ao.longitude    AS origin_lng,
  r.destination_code,
  ad.city         AS dest_city,
  ad.name         AS dest_airport,
  ad.state        AS dest_state,
  ad.region       AS dest_region,
  ad.latitude     AS dest_lat,
  ad.longitude    AS dest_lng,
  r.distance_km,
  r.avg_duration_min,
  r.airlines,
  r.min_price_inr,
  r.avg_price_inr,
  r.max_price_inr,
  r.flights_per_day,
  r.is_popular
FROM public.routes r
JOIN public.airports ao ON r.origin_code      = ao.iata_code
JOIN public.airports ad ON r.destination_code = ad.iata_code
WHERE ao.country_code = 'IN'
  AND ad.country_code = 'IN'
  AND r.is_active = TRUE
ORDER BY r.flights_per_day DESC;

-- ================================================================
-- STEP 19: ROUTES DATA
-- ================================================================
INSERT INTO public.routes (origin_code,destination_code,distance_km,avg_duration_min,airlines,min_price_inr,avg_price_inr,max_price_inr,flights_per_day,is_popular)
VALUES
('DEL','BOM',1148,120,'{AI,6E,SG,UK,QP}',2799,6200,18000,32,TRUE),
('DEL','BLR',1740,155,'{AI,6E,SG,UK,QP}',3299,7000,20000,26,TRUE),
('DEL','MAA',1760,160,'{AI,6E,SG,UK,QP}',3499,7500,22000,20,TRUE),
('DEL','HYD',1253,130,'{AI,6E,SG,UK,QP}',3099,6600,19000,22,TRUE),
('DEL','CCU',1305,130,'{AI,6E,SG,UK}',2999,5900,17000,18,TRUE),
('DEL','COK',2210,195,'{AI,6E,SG}',4299,9000,26000,10,FALSE),
('DEL','GOI',1892,175,'{AI,6E,SG,UK}',3799,8200,24000,10,FALSE),
('DEL','JAI',258,55,'{AI,6E,SG,UK,QP}',1399,3100,9000,16,FALSE),
('DEL','LKO',492,65,'{AI,6E,SG,UK}',1599,3600,10000,14,FALSE),
('DEL','AMD',909,90,'{AI,6E,SG,UK,QP}',2099,4600,13000,12,FALSE),
('DEL','ATQ',440,65,'{AI,6E,SG}',1499,3200,9500,8,FALSE),
('DEL','IXC',247,50,'{AI,6E,SG}',1199,2700,8000,10,FALSE),
('DEL','SXR',890,80,'{AI,6E,SG}',2399,5000,15000,10,FALSE),
('DEL','IXJ',560,65,'{AI,6E,SG}',1699,3700,10500,8,FALSE),
('DEL','IXL',1054,85,'{AI,6E}',2999,5800,16500,6,FALSE),
('DEL','DED',267,55,'{AI,6E}',1299,2900,8200,6,FALSE),
('DEL','GAU',1580,150,'{AI,6E,SG}',3499,7300,21000,8,FALSE),
('DEL','BBI',1610,150,'{AI,6E,SG}',3199,6700,18500,8,FALSE),
('DEL','VNS',676,75,'{AI,6E,SG}',1799,4000,11000,8,FALSE),
('DEL','PAT',990,100,'{AI,6E,SG}',2199,4700,13500,10,FALSE),
('DEL','IXR',1260,125,'{AI,6E}',2799,5700,16000,6,FALSE),
('DEL','BHO',697,80,'{AI,6E,SG}',1899,4100,11500,6,FALSE),
('DEL','IDR',778,85,'{AI,6E,SG}',1999,4300,12000,6,FALSE),
('DEL','NAG',1083,115,'{AI,6E,SG}',2299,4900,13800,6,FALSE),
('DEL','RPR',1120,115,'{AI,6E}',2499,5200,14500,4,FALSE),
('DEL','TRV',2240,205,'{AI,6E}',4599,9600,27000,4,FALSE),
('DEL','IXZ',2008,183,'{AI,6E}',4099,8700,24500,4,FALSE),
('DEL','VTZ',1393,132,'{AI,6E,SG}',2999,6200,17500,6,FALSE),
('DEL','IMF',2098,188,'{AI,6E}',3999,8100,22500,4,FALSE),
('DEL','JDH',596,70,'{AI,6E,SG}',1799,3800,10800,4,FALSE),
('DEL','UDR',654,75,'{AI,6E}',1899,4000,11300,4,FALSE),
('DEL','PNQ',1397,130,'{AI,6E,SG,UK}',2999,6000,17000,10,FALSE),
('BOM','BLR',845,85,'{AI,6E,SG,UK,QP}',2399,5100,15000,26,TRUE),
('BOM','MAA',1040,100,'{AI,6E,SG,UK,QP}',2599,5400,16000,20,FALSE),
('BOM','HYD',621,70,'{AI,6E,SG,UK,QP}',2099,4400,13000,22,TRUE),
('BOM','CCU',1658,155,'{AI,6E,SG,UK}',3399,7100,21000,14,FALSE),
('BOM','COK',1209,115,'{AI,6E,SG,UK}',2799,5700,17000,14,FALSE),
('BOM','GOI',467,55,'{AI,6E,SG,UK,QP}',1699,3600,10500,12,FALSE),
('BOM','MYA',536,65,'{AI,6E,SG,QP}',1799,3800,10900,8,FALSE),
('BOM','AMD',471,60,'{AI,6E,SG,UK,QP}',1499,3200,9500,16,FALSE),
('BOM','PNQ',119,40,'{AI,6E,SG}',899,2100,7000,10,FALSE),
('BOM','JAI',1050,105,'{AI,6E,SG,UK}',2399,5000,14000,8,FALSE),
('BOM','IDR',509,65,'{AI,6E,SG}',1699,3600,10500,6,FALSE),
('BOM','NAG',830,85,'{AI,6E,SG}',2199,4600,13000,8,FALSE),
('BOM','TRV',1383,127,'{AI,6E,SG}',2999,6100,17500,8,FALSE),
('BOM','TRZ',1296,123,'{AI,6E}',2899,5900,16800,4,FALSE),
('BOM','CJB',979,101,'{AI,6E,SG}',2299,4800,13700,6,FALSE),
('BOM','IXE',340,53,'{AI,6E,IX}',1199,2600,7500,8,FALSE),
('BOM','IXZ',2136,197,'{AI,6E}',4199,8600,24200,2,FALSE),
('BOM','BBI',1648,153,'{AI,6E,SG}',3399,6900,19500,6,FALSE),
('BOM','LKO',1177,115,'{AI,6E,SG}',2699,5500,15500,6,FALSE),
('BOM','PAT',1570,146,'{AI,6E}',3299,6700,18900,4,FALSE),
('BOM','GAU',2147,198,'{AI,6E}',4199,8600,24000,4,FALSE),
('BOM','TIR',1316,124,'{AI,6E}',2899,5900,16600,4,FALSE),
('BOM','VTZ',1175,115,'{AI,6E}',2699,5500,15600,4,FALSE),
('BOM','VGA',1127,112,'{AI,6E}',2599,5300,15000,4,FALSE),
('BOM','CCJ',1532,142,'{AI,6E,IX}',3299,6700,18900,4,FALSE),
('BOM','CNN',1602,148,'{AI,6E,IX}',3399,6900,19400,2,FALSE),
('BLR','MAA',290,50,'{AI,6E,SG,UK,QP}',1199,2600,8000,22,TRUE),
('BLR','HYD',498,60,'{AI,6E,SG,UK,QP}',1399,3000,9000,20,FALSE),
('BLR','CCU',1560,148,'{AI,6E,SG}',3299,6700,19000,10,FALSE),
('BLR','COK',360,55,'{AI,6E,SG,UK,IX}',1299,2800,8500,16,FALSE),
('BLR','TRV',218,45,'{AI,6E,SG,IX}',1099,2400,7400,12,FALSE),
('BLR','TRZ',275,50,'{AI,6E,SG}',1199,2600,7800,8,FALSE),
('BLR','IXM',369,55,'{AI,6E}',1399,3000,8800,6,FALSE),
('BLR','CJB',247,50,'{AI,6E,SG}',1099,2400,7200,8,FALSE),
('BLR','IXE',225,45,'{AI,6E,IX}',1099,2400,7200,8,FALSE),
('BLR','MYQ',143,38,'{AI,6E}',999,2200,6700,6,FALSE),
('BLR','VTZ',645,75,'{AI,6E}',1899,4000,11500,6,FALSE),
('BLR','VGA',625,72,'{AI,6E}',1799,3800,10800,4,FALSE),
('BLR','TIR',286,52,'{AI,6E}',1199,2600,7800,6,FALSE),
('BLR','GOI',548,65,'{AI,6E,SG}',1699,3600,10500,8,FALSE),
('BLR','NAG',966,100,'{AI,6E}',2299,4700,13300,4,FALSE),
('BLR','BBI',1067,110,'{AI,6E}',2499,5100,14400,4,FALSE),
('BLR','GAU',2082,193,'{AI,6E}',4099,8400,23600,4,FALSE),
('BLR','IXZ',1764,163,'{AI,6E}',3599,7300,20600,2,FALSE),
('BLR','CCJ',472,63,'{AI,6E,IX}',1499,3200,9200,6,FALSE),
('BLR','CNN',518,67,'{AI,6E,IX}',1599,3400,9700,4,FALSE),
('MAA','HYD',521,63,'{AI,6E,SG,UK,QP}',1499,3200,9500,16,FALSE),
('MAA','CCU',1369,132,'{AI,6E,SG}',2899,5900,17000,10,FALSE),
('MAA','COK',520,63,'{AI,6E,SG,IX}',1599,3400,10000,12,FALSE),
('MAA','TRV',450,60,'{AI,6E,SG,IX}',1399,2900,9000,10,FALSE),
('MAA','TRZ',315,52,'{AI,6E,SG}',1199,2600,7800,8,FALSE),
('MAA','IXM',330,53,'{AI,6E}',1299,2800,8300,6,FALSE),
('MAA','CJB',493,63,'{AI,6E}',1599,3400,9700,8,FALSE),
('MAA','VTZ',592,70,'{AI,6E}',1799,3800,10700,6,FALSE),
('MAA','TIR',181,42,'{AI,6E}',899,2000,6200,6,FALSE),
('MAA','BBI',1066,110,'{AI,6E}',2499,5100,14400,6,FALSE),
('MAA','IXZ',1372,132,'{AI,6E}',2999,6100,17300,4,FALSE),
('MAA','IXE',561,68,'{AI,6E,IX}',1699,3600,10200,6,FALSE),
('MAA','CCJ',735,83,'{AI,6E,IX}',1999,4200,11900,6,FALSE),
('MAA','CNN',781,87,'{AI,6E,IX}',2099,4400,12400,4,FALSE),
('MAA','GOP',1764,164,'{AI,6E}',3599,7300,20500,4,FALSE),
('HYD','CCU',1285,127,'{AI,6E,SG}',2799,5700,16200,8,FALSE),
('HYD','COK',884,90,'{AI,6E,SG}',2099,4500,12800,8,FALSE),
('HYD','VTZ',347,53,'{AI,6E,SG}',1399,3000,8800,8,FALSE),
('HYD','VGA',275,50,'{AI,6E}',1199,2600,7700,6,FALSE),
('HYD','NAG',629,73,'{AI,6E}',1899,4000,11300,6,FALSE),
('HYD','BBI',1010,105,'{AI,6E}',2399,4900,13900,6,FALSE),
('HYD','TRV',1115,112,'{AI,6E}',2599,5300,15000,6,FALSE),
('HYD','IXZ',1701,158,'{AI,6E}',3499,7100,20000,2,FALSE),
('HYD','IMF',1598,150,'{AI,6E}',3299,6700,18900,2,FALSE),
('HYD','RJA',424,60,'{AI,6E}',1499,3200,9200,4,FALSE),
('CCU','GAU',430,60,'{AI,6E,SG}',1599,3400,9700,12,FALSE),
('CCU','IXB',583,70,'{AI,6E}',1799,3800,10800,6,FALSE),
('CCU','PAT',513,65,'{AI,6E}',1699,3600,10200,6,FALSE),
('CCU','BBI',440,60,'{AI,6E,SG}',1499,3200,9200,8,FALSE),
('CCU','IXR',341,55,'{AI,6E,SG}',1399,3000,8700,6,FALSE),
('CCU','IMF',1006,105,'{AI,6E}',2399,4900,13900,4,FALSE),
('CCU','IXA',359,57,'{AI,6E}',1499,3200,9200,6,FALSE),
('CCU','DIB',614,73,'{AI,6E}',1799,3800,10800,4,FALSE),
('CCU','IXZ',1255,122,'{AI,6E}',2899,5900,16700,4,FALSE),
('CCU','GAY',517,67,'{AI,6E}',1699,3600,10300,4,FALSE),
('CCU','IXS',554,70,'{AI,6E}',1799,3800,10800,4,FALSE),
('CCU','SHL',371,58,'{AI,6E}',1499,3200,9200,4,FALSE),
('GAU','IMF',499,66,'{AI,6E}',1699,3600,10300,4,FALSE),
('GAU','IXA',326,53,'{AI,6E}',1299,2800,8200,4,FALSE),
('GAU','DIB',439,61,'{AI,6E}',1599,3400,9700,4,FALSE),
('GAU','IXS',370,57,'{AI,6E}',1499,3200,9200,4,FALSE),
('GAU','DMU',446,62,'{AI,6E}',1599,3400,9700,4,FALSE),
('GAU','TEZ',174,40,'{AI,6E}',899,2000,6200,4,FALSE),
('GAU','JRH',311,53,'{AI,6E}',1299,2800,8200,4,FALSE),
('GAU','IXI',287,51,'{AI,6E}',1199,2600,7700,4,FALSE),
('GAU','SHL',102,33,'{AI,6E}',799,1900,5900,4,FALSE),
('GAU','IXB',284,51,'{AI,6E}',1199,2600,7700,4,FALSE),
('GAU','AJL',366,57,'{AI,6E}',1399,3000,8700,2,FALSE),
('GAU','IXR',1192,115,'{AI,6E}',2699,5500,15500,2,FALSE),
('COK','TRV',215,42,'{AI,6E,SG,IX}',899,2000,6300,12,FALSE),
('COK','TRZ',410,57,'{6E,SG,IX}',1299,2800,8300,6,FALSE),
('COK','IXE',190,40,'{AI,6E,IX}',899,2000,6200,6,FALSE),
('COK','CJB',165,38,'{AI,6E}',899,2000,6200,4,FALSE),
('COK','CCJ',183,42,'{AI,6E,IX}',899,2000,6300,8,FALSE),
('COK','CNN',233,47,'{AI,6E,IX}',1099,2400,7200,6,FALSE),
('COK','AGX',1241,120,'{AI,IX}',2799,5700,16100,4,FALSE),
('COK','IXM',467,63,'{AI,6E,IX}',1499,3200,9100,4,FALSE),
('AMD','JAI',562,68,'{AI,6E,SG}',1699,3600,10300,6,FALSE),
('AMD','IDR',295,52,'{AI,6E}',1199,2600,7700,4,FALSE),
('AMD','UDR',241,47,'{AI,6E}',1099,2400,7200,4,FALSE),
('AMD','BDQ',106,33,'{AI,6E}',699,1700,5400,6,FALSE),
('AMD','BHJ',293,52,'{AI,6E}',1199,2600,7700,4,FALSE),
('AMD','JDH',494,64,'{AI,6E}',1599,3400,9700,4,FALSE),
('AMD','RAJ',196,43,'{AI,6E}',999,2200,6700,4,FALSE),
('AMD','STV',264,50,'{AI,6E}',1099,2400,7200,4,FALSE),
('TRV','CJB',399,58,'{AI,6E}',1499,3200,9200,4,FALSE),
('TRV','TRZ',273,50,'{AI,6E}',1099,2400,7200,4,FALSE),
('TRV','IXM',502,66,'{AI,6E}',1599,3400,9700,4,FALSE),
('CJB','TRZ',220,44,'{AI,6E}',999,2200,6700,4,FALSE),
('CJB','CCJ',248,48,'{AI,6E,IX}',1099,2400,7200,4,FALSE),
('TRZ','IXM',101,32,'{AI,6E}',699,1700,5400,4,FALSE),
('CCJ','CNN',136,36,'{AI,6E,IX}',799,1900,5900,6,FALSE),
('VGA','VTZ',214,44,'{AI,6E}',999,2200,6700,4,FALSE),
('VTZ','RJA',147,38,'{AI,6E}',799,1900,5900,4,FALSE),
('IXE','GOI',439,62,'{AI,6E}',1599,3400,9700,4,FALSE),
('IXE','HBX',147,37,'{AI,6E}',799,1900,5900,4,FALSE),
('TIR','HYD',310,53,'{AI,6E}',1199,2600,7700,6,FALSE),
('IXJ','SXR',301,52,'{AI,6E}',1199,2600,7700,4,FALSE),
('IXJ','IXL',432,62,'{AI,6E}',1599,3400,9700,2,FALSE),
('SXR','IXL',288,51,'{AI,6E}',1099,2400,7200,4,FALSE),
('SXR','ATQ',330,53,'{AI,6E}',1299,2800,8200,4,FALSE),
('ATQ','IXC',115,35,'{AI,6E}',699,1700,5400,4,FALSE),
('JAI','JDH',277,51,'{AI,6E}',1099,2400,7200,4,FALSE),
('JAI','UDR',403,59,'{AI,6E}',1499,3200,9200,2,FALSE),
('JAI','JSA',492,67,'{AI,6E}',1599,3400,9700,2,FALSE),
('BHO','IDR',189,42,'{AI,6E}',899,2000,6200,4,FALSE),
('BHO','NAG',354,56,'{AI,6E}',1399,3000,8700,2,FALSE),
('PAT','IXR',294,52,'{AI,6E}',1199,2600,7700,4,FALSE),
('PAT','GAY',150,38,'{AI,6E}',799,1900,5900,4,FALSE),
('BBI','RPR',430,61,'{AI,6E}',1599,3400,9700,4,FALSE),
('BBI','IXR',441,61,'{AI,6E}',1599,3400,9700,4,FALSE),
('RPR','NAG',452,62,'{AI,6E}',1599,3400,9700,2,FALSE),
('IXR','PAT',294,52,'{AI,6E}',1199,2600,7700,4,FALSE),
('IXZ','MAA',1372,132,'{AI,6E}',2999,6100,17300,4,FALSE),
('IXZ','HYD',1701,158,'{AI,6E}',3499,7100,20000,2,FALSE),
('AGX','COK',1241,120,'{AI,IX}',2799,5700,16100,4,FALSE),
('AGX','MAA',1636,152,'{AI,IX}',3299,6700,18900,2,FALSE),
('GOI','MAA',1009,104,'{AI,6E,SG}',2399,4900,13900,4,FALSE),
('GOI','HYD',525,66,'{AI,6E,SG}',1699,3600,10200,4,FALSE),
('GOI','BBI',1267,123,'{AI,6E}',2799,5700,16100,2,FALSE),
('IMF','DMU',259,49,'{AI,6E}',1099,2400,7200,2,FALSE),
('DIB','JRH',145,37,'{AI,6E}',799,1900,5900,2,FALSE),
('IXA','SHL',355,56,'{AI,6E}',1399,3000,8700,2,FALSE),
('AJL','IXA',299,52,'{AI,6E}',1199,2600,7700,2,FALSE),
('TEZ','DIB',127,36,'{AI,6E}',699,1700,5400,2,FALSE),
('JRH','GAU',311,53,'{AI,6E}',1299,2800,8200,4,FALSE)
ON CONFLICT (origin_code,destination_code) DO UPDATE SET
  airlines=EXCLUDED.airlines, min_price_inr=EXCLUDED.min_price_inr,
  avg_price_inr=EXCLUDED.avg_price_inr, max_price_inr=EXCLUDED.max_price_inr,
  flights_per_day=EXCLUDED.flights_per_day, is_popular=EXCLUDED.is_popular;

-- Auto-generate reverse (return) routes
INSERT INTO public.routes (origin_code,destination_code,distance_km,avg_duration_min,airlines,min_price_inr,avg_price_inr,max_price_inr,flights_per_day,is_popular)
SELECT destination_code,origin_code,distance_km,avg_duration_min,airlines,min_price_inr,avg_price_inr,max_price_inr,flights_per_day,is_popular
FROM public.routes
ON CONFLICT (origin_code,destination_code) DO NOTHING;

-- ================================================================
-- STEP 20: FINAL VERIFICATION QUERY
-- ================================================================
DO $$
DECLARE
  v_airports  INT;
  v_airlines  INT;
  v_routes    INT;
  v_coupons   INT;
BEGIN
  SELECT COUNT(*) INTO v_airports FROM public.airports WHERE country_code = 'IN';
  SELECT COUNT(*) INTO v_airlines FROM public.airlines;
  SELECT COUNT(*) INTO v_routes   FROM public.routes;
  SELECT COUNT(*) INTO v_coupons  FROM public.coupons;
  RAISE NOTICE '====================================';
  RAISE NOTICE 'SkyMind DB Setup Complete!';
  RAISE NOTICE 'Indian airports : %', v_airports;
  RAISE NOTICE 'Airlines        : %', v_airlines;
  RAISE NOTICE 'Total routes    : %', v_routes;
  RAISE NOTICE 'Coupons         : %', v_coupons;
  RAISE NOTICE '====================================';
END $$;
