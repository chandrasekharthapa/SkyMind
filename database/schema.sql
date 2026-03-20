-- ============================================================
-- SkyMind Flight AI Platform — ADVANCED Database Schema v2
-- Includes: All India domestic routes, airports, airlines,
--           full auth system, Gmail/SMS notifications
-- Run in Supabase SQL Editor
-- ============================================================

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "unaccent";

-- ============================================================
-- AIRPORTS — All 35 Indian domestic + major international
-- ============================================================
CREATE TABLE IF NOT EXISTS public.airports (
  iata_code        TEXT PRIMARY KEY,
  icao_code        TEXT,
  name             TEXT NOT NULL,
  city             TEXT NOT NULL,
  state            TEXT,
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
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- All Indian domestic airports
INSERT INTO airports (iata_code,icao_code,name,city,state,country,country_code,latitude,longitude,is_domestic,is_international,elevation_ft,terminal_count) VALUES
-- Metro airports
('DEL','VIDP','Indira Gandhi International Airport','New Delhi','Delhi','India','IN',28.5665,77.1031,true,true,777,3),
('BOM','VABB','Chhatrapati Shivaji Maharaj International Airport','Mumbai','Maharashtra','India','IN',19.0896,72.8656,true,true,37,2),
('BLR','VOBL','Kempegowda International Airport','Bengaluru','Karnataka','India','IN',13.1986,77.7066,true,true,3000,2),
('MAA','VOMM','Chennai International Airport','Chennai','Tamil Nadu','India','IN',12.9900,80.1693,true,true,52,4),
('HYD','VOHS','Rajiv Gandhi International Airport','Hyderabad','Telangana','India','IN',17.2313,78.4298,true,true,2024,1),
('CCU','VECC','Netaji Subhas Chandra Bose International Airport','Kolkata','West Bengal','India','IN',22.6520,88.4463,true,true,19,2),
-- Tier 2 cities
('COK','VOCI','Cochin International Airport','Kochi','Kerala','India','IN',10.1520,76.4019,true,true,30,2),
('PNQ','VAPO','Pune Airport','Pune','Maharashtra','India','IN',18.5821,73.9197,true,false,1942,1),
('AMD','VAAH','Sardar Vallabhbhai Patel International Airport','Ahmedabad','Gujarat','India','IN',23.0772,72.6347,true,true,189,2),
('GOI','VAGO','Goa International Airport (Dabolim)','Goa','Goa','India','IN',15.3808,73.8314,true,true,150,1),
('JAI','VIJP','Jaipur International Airport','Jaipur','Rajasthan','India','IN',26.8242,75.8122,true,true,1263,2),
('LKO','VILK','Chaudhary Charan Singh International Airport','Lucknow','Uttar Pradesh','India','IN',26.7606,80.8893,true,true,410,1),
('PAT','VEPT','Jay Prakash Narayan Airport','Patna','Bihar','India','IN',25.5913,85.0880,true,false,170,1),
('BHO','VABP','Raja Bhoj Airport','Bhopal','Madhya Pradesh','India','IN',23.2875,77.3374,true,false,1711,1),
('NAG','VANP','Dr. Babasaheb Ambedkar International Airport','Nagpur','Maharashtra','India','IN',21.0922,79.0473,true,true,1033,1),
('IXC','VICG','Chandigarh International Airport','Chandigarh','Punjab','India','IN',30.6735,76.7885,true,false,1012,1),
('SXR','VISR','Sheikh ul-Alam International Airport','Srinagar','Jammu & Kashmir','India','IN',33.9871,74.7742,true,false,5429,1),
('ATQ','VIAR','Sri Guru Ram Dass Jee International Airport','Amritsar','Punjab','India','IN',31.7096,74.7973,true,true,756,1),
('IXB','VEBD','Bagdogra Airport','Siliguri','West Bengal','India','IN',26.6812,88.3286,true,false,412,1),
('GAU','VEGT','Lokpriya Gopinath Bordoloi International Airport','Guwahati','Assam','India','IN',26.1061,91.5859,true,true,162,1),
('IMF','VEIM','Imphal Airport','Imphal','Manipur','India','IN',24.7600,93.8967,true,false,2539,1),
('DIB','VEMN','Dibrugarh Airport','Dibrugarh','Assam','India','IN',27.4839,95.0169,true,false,362,1),
('IXZ','VOPB','Veer Savarkar International Airport','Port Blair','Andaman & Nicobar','India','IN',11.6412,92.7297,true,false,14,1),
('TRV','VOTV','Trivandrum International Airport','Thiruvananthapuram','Kerala','India','IN',8.4782,76.9201,true,true,15,1),
('TRZ','VOTR','Tiruchirappalli International Airport','Tiruchirappalli','Tamil Nadu','India','IN',10.7654,78.7097,true,true,88,1),
('IXM','VOMD','Madurai Airport','Madurai','Tamil Nadu','India','IN',9.8345,78.0934,true,false,459,1),
('VTZ','VEVZ','Visakhapatnam Airport','Visakhapatnam','Andhra Pradesh','India','IN',17.7212,83.2245,true,false,15,1),
('BBI','VEBS','Biju Patnaik International Airport','Bhubaneswar','Odisha','India','IN',20.2444,85.8178,true,false,148,1),
('IXR','VERC','Birsa Munda Airport','Ranchi','Jharkhand','India','IN',23.3143,85.3217,true,false,2148,1),
('VNS','VIBN','Lal Bahadur Shastri Airport','Varanasi','Uttar Pradesh','India','IN',25.4524,82.8593,true,false,266,1),
('IDR','VAID','Devi Ahilyabai Holkar Airport','Indore','Madhya Pradesh','India','IN',22.7218,75.8011,true,false,1850,1),
('UDR','VAUD','Maharana Pratap Airport','Udaipur','Rajasthan','India','IN',24.6177,73.8961,true,false,1684,1),
('JDH','VEJD','Jodhpur Airport','Jodhpur','Rajasthan','India','IN',26.2511,73.0489,true,false,717,1),
('KNU','VIKA','Kanpur Airport','Kanpur','Uttar Pradesh','India','IN',26.4044,80.3649,true,false,410,1),
('AGR','VIAG','Agra Airport','Agra','Uttar Pradesh','India','IN',27.1558,77.9609,true,false,551,1),
('IXJ','VIJU','Jammu Airport','Jammu','Jammu & Kashmir','India','IN',32.6891,74.8374,true,false,1029,1),
('DHM','VIDD','Gaggal Airport','Dharamshala','Himachal Pradesh','India','IN',32.1651,76.2634,true,false,2525,1),
('SHL','VESL','Shillong Airport','Shillong','Meghalaya','India','IN',25.7036,91.9787,true,false,2910,1),
('IXA','VEAT','Agartala Airport','Agartala','Tripura','India','IN',23.8870,91.2404,true,false,46,1),
('IXI','VELP','Lilabari Airport','Lakhimpur','Assam','India','IN',27.2955,94.0976,true,false,330,1),
('HBX','VOHB','Hubli Airport','Hubballi','Karnataka','India','IN',15.3617,75.0849,true,false,2171,1),
('MYQ','VOYK','Mysore Airport','Mysuru','Karnataka','India','IN',12.2308,76.6496,true,false,2469,1),
('IXE','VOMN','Mangalore International Airport','Mangalore','Karnataka','India','IN',12.9613,74.8904,true,true,337,1),
('GOP','VEGP','Gorakhpur Airport','Gorakhpur','Uttar Pradesh','India','IN',26.7397,83.4497,true,false,259,1),
('RPR','VARP','Swami Vivekananda Airport','Raipur','Chhattisgarh','India','IN',21.1804,81.7388,true,false,1041,1),
-- New greenfield airports
('HIA','VOHL','Hindon Airport','Ghaziabad','Uttar Pradesh','India','IN',28.6927,77.4278,true,false,709,1),
('MYA','VOMY','Mopa Airport (Goa International)','Mopa','Goa','India','IN',15.7127,73.8651,true,true,200,1),
-- Key international hubs (for hidden route detection)
('DXB','OMDB','Dubai International Airport','Dubai','Dubai','UAE','AE',25.2532,55.3657,false,true,62,3),
('SIN','WSSS','Changi Airport','Singapore','Singapore','SG','SG',1.3644,103.9915,false,true,22,4),
('LHR','EGLL','Heathrow Airport','London','England','UK','GB',51.4700,-0.4543,false,true,83,5),
('CDG','LFPG','Charles de Gaulle Airport','Paris','Île-de-France','France','FR',49.0097,2.5479,false,true,392,4),
('BKK','VTBS','Suvarnabhumi Airport','Bangkok','Bangkok','Thailand','TH',13.6900,100.7501,false,true,5,2),
('IST','LTFM','Istanbul Airport','Istanbul','Istanbul','Turkey','TR',41.2608,28.7418,false,true,325,1),
('NRT','RJAA','Narita International Airport','Tokyo','Kanto','Japan','JP',35.7720,140.3929,false,true,135,3),
('JFK','KJFK','John F. Kennedy International Airport','New York','New York','USA','US',40.6413,-73.7781,false,true,13,6),
('DOH','OTHH','Hamad International Airport','Doha','Ad Dawhah','Qatar','QA',25.2731,51.6080,false,true,13,1),
('KUL','WMKK','Kuala Lumpur International Airport','Kuala Lumpur','Kuala Lumpur','Malaysia','MY',2.7456,101.7099,false,true,69,2)
ON CONFLICT (iata_code) DO UPDATE SET
  name=EXCLUDED.name, city=EXCLUDED.city, latitude=EXCLUDED.latitude, longitude=EXCLUDED.longitude;

-- ============================================================
-- AIRLINES — All Indian carriers + major international
-- ============================================================
CREATE TABLE IF NOT EXISTS public.airlines (
  iata_code     TEXT PRIMARY KEY,
  icao_code     TEXT,
  name          TEXT NOT NULL,
  country       TEXT DEFAULT 'India',
  is_domestic   BOOLEAN DEFAULT TRUE,
  is_lowcost    BOOLEAN DEFAULT FALSE,
  hub_airport   TEXT REFERENCES airports(iata_code),
  website       TEXT,
  contact_phone TEXT,
  logo_url      TEXT,
  is_active     BOOLEAN DEFAULT TRUE,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO airlines (iata_code,icao_code,name,country,is_domestic,is_lowcost,hub_airport,website,contact_phone) VALUES
('AI','AIC','Air India','India',true,false,'DEL','https://airindia.com','+91-11-24622220'),
('6E','IGO','IndiGo','India',true,true,'DEL','https://goindigo.in','+91-99-10383838'),
('SG','SEJ','SpiceJet','India',true,true,'DEL','https://spicejet.com','+91-98-71803333'),
('UK','TAI','Vistara','India',true,false,'DEL','https://airvistara.com','+91-92-89228922'),
('IX','MDV','Air India Express','India',true,true,'COK','https://airindiaexpress.in','+91-95-55888840'),
('QP','AQP','Akasa Air','India',true,true,'BOM','https://akasaair.com','+91-86-52001000'),
('S5','SNJ','Star Air','India',true,false,'BLR','https://starair.in','+91-86-50009000'),
('2T','TLB','TruJet','India',true,true,'HYD','https://trujet.com','+91-40-44334433'),
('I7','DAI','Alliance Air','India',true,false,'DEL','https://allianceair.in','+91-11-42255255'),
-- International
('EK','UAE','Emirates','UAE',false,false,'DXB','https://emirates.com','+971-600555555'),
('SQ','SIA','Singapore Airlines','Singapore',false,false,'SIN','https://singaporeair.com','+65-62238888'),
('QR','QTR','Qatar Airways','Qatar',false,false,'DOH','https://qatarairways.com','+974-40221111'),
('BA','BAW','British Airways','UK',false,false,'LHR','https://britishairways.com','+44-3444930787'),
('TK','THY','Turkish Airlines','Turkey',false,false,'IST','https://turkishairlines.com','+90-8503330849')
ON CONFLICT (iata_code) DO UPDATE SET name=EXCLUDED.name;

-- ============================================================
-- DOMESTIC ROUTES — All major India domestic pairs
-- ============================================================
CREATE TABLE IF NOT EXISTS public.routes (
  id              UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  origin_code     TEXT NOT NULL REFERENCES airports(iata_code),
  destination_code TEXT NOT NULL REFERENCES airports(iata_code),
  distance_km     INT,
  avg_duration_min INT,
  is_active       BOOLEAN DEFAULT TRUE,
  airlines        TEXT[],  -- operating airline codes
  min_price_inr   DECIMAL(10,2),
  avg_price_inr   DECIMAL(10,2),
  max_price_inr   DECIMAL(10,2),
  flights_per_day INT DEFAULT 1,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(origin_code, destination_code)
);

-- Major domestic routes (bidirectional — app queries both directions)
INSERT INTO routes (origin_code,destination_code,distance_km,avg_duration_min,airlines,min_price_inr,avg_price_inr,max_price_inr,flights_per_day) VALUES
-- DEL hub routes
('DEL','BOM',1148,125,'{AI,6E,SG,UK,QP}',2999,6500,18000,28),
('DEL','BLR',1740,160,'{AI,6E,SG,UK,QP}',3499,7200,20000,22),
('DEL','MAA',1760,165,'{AI,6E,SG,UK}',3799,7800,22000,18),
('DEL','HYD',1253,135,'{AI,6E,SG,UK,QP}',3299,6800,19000,20),
('DEL','CCU',1305,135,'{AI,6E,SG,UK}',3199,6200,17000,16),
('DEL','COK',2210,200,'{AI,6E,SG}',4499,9200,25000,10),
('DEL','GOI',1892,180,'{AI,6E,SG,UK}',3999,8500,24000,8),
('DEL','JAI',258,60,'{AI,6E,SG,UK,QP}',1499,3200,9000,14),
('DEL','LKO',492,70,'{AI,6E,SG,UK}',1699,3800,10000,12),
('DEL','AMD',909,95,'{AI,6E,SG,QP}',2199,4800,13000,10),
('DEL','PNQ',1397,135,'{AI,6E,SG}',3099,6200,17000,8),
('DEL','IXC',247,55,'{AI,6E}',1299,2800,8000,8),
('DEL','ATQ',440,70,'{AI,6E,SG}',1599,3400,9500,6),
('DEL','SXR',890,85,'{AI,6E,SG}',2499,5200,15000,8),
('DEL','GAU',1580,155,'{AI,6E}',3699,7500,21000,6),
('DEL','BBI',1610,155,'{AI,6E,SG}',3399,6900,18000,6),
('DEL','VNS',676,80,'{AI,6E}',1899,4200,11000,6),
('DEL','IXR',1260,130,'{AI,6E}',2899,5900,16000,4),
('DEL','PAT',990,105,'{AI,6E,SG}',2299,4900,13500,8),
('DEL','RPR',1120,120,'{AI,6E}',2599,5400,14500,4),
('DEL','IDR',778,90,'{AI,6E}',2099,4500,12000,4),
('DEL','NAG',1083,120,'{AI,6E}',2399,5100,13800,4),
('DEL','IXJ',560,70,'{AI,6E}',1799,3900,10500,8),
('DEL','TRV',2240,210,'{AI,6E}',4799,9800,27000,4),
('DEL','IXZ',2008,190,'{AI}',4299,8900,24000,2),
-- BOM hub routes
('BOM','BLR',845,90,'{AI,6E,SG,UK,QP}',2499,5200,15000,24),
('BOM','MAA',1040,105,'{AI,6E,SG,UK,QP}',2699,5600,16000,18),
('BOM','HYD',621,75,'{AI,6E,SG,UK,QP}',2199,4600,13000,20),
('BOM','CCU',1658,160,'{AI,6E,SG}',3599,7400,21000,12),
('BOM','COK',1209,120,'{AI,6E,SG,UK}',2899,5900,17000,12),
('BOM','GOI',467,60,'{AI,6E,SG,QP}',1799,3700,10500,10),
('BOM','AMD',471,65,'{AI,6E,SG,UK,QP}',1599,3300,9500,14),
('BOM','PNQ',119,45,'{AI,6E,SG}',999,2200,7000,8),
('BOM','JAI',1050,110,'{AI,6E,SG}',2499,5100,14000,6),
('BOM','IDR',509,70,'{AI,6E}',1799,3800,10500,4),
('BOM','NAG',830,90,'{AI,6E,SG}',2299,4700,13000,6),
('BOM','BBI',1648,160,'{AI,6E}',3499,7100,19500,4),
('BOM','IXR',1621,155,'{AI,6E}',3399,6900,18500,2),
('BOM','VTZ',1064,110,'{AI,6E}',2599,5300,14500,4),
('BOM','LKO',1177,120,'{AI,6E}',2799,5700,15500,4),
('BOM','TRV',1383,130,'{AI,6E,SG}',3099,6200,17500,6),
-- BLR hub routes
('BLR','MAA',290,55,'{AI,6E,SG,UK,QP}',1299,2700,8000,20),
('BLR','HYD',498,65,'{AI,6E,SG,UK,QP}',1499,3100,9000,18),
('BLR','CCU',1560,155,'{AI,6E,SG}',3399,6900,19000,8),
('BLR','COK',360,60,'{AI,6E,SG,UK}',1399,2900,8500,14),
('BLR','GOI',548,70,'{AI,6E,SG}',1799,3700,10500,6),
('BLR','AMD',1324,135,'{AI,6E}',2999,6100,17000,4),
('BLR','TRV',218,50,'{AI,6E,SG}',1199,2500,7500,10),
('BLR','TRZ',275,55,'{AI,6E}',1299,2700,7800,6),
('BLR','IXM',369,60,'{AI,6E}',1499,3100,8800,4),
('BLR','VTZ',645,80,'{AI,6E}',1999,4100,11500,4),
('BLR','IXE',225,50,'{AI,6E}',1199,2500,7200,6),
-- MAA hub routes
('MAA','HYD',521,70,'{AI,6E,SG,UK}',1599,3300,9500,14),
('MAA','CCU',1369,140,'{AI,6E,SG}',2999,6100,17000,8),
('MAA','COK',520,70,'{AI,6E,SG}',1699,3500,10000,10),
('MAA','TRV',450,65,'{AI,6E,SG}',1499,3100,9000,8),
('MAA','TRZ',315,55,'{AI,6E}',1299,2700,7800,6),
('MAA','IXM',330,60,'{AI,6E}',1399,2900,8300,4),
('MAA','BBI',1066,115,'{AI,6E}',2599,5300,14800,4),
('MAA','VTZ',592,75,'{AI,6E}',1799,3700,10500,4),
-- HYD hub routes
('HYD','CCU',1285,135,'{AI,6E,SG}',2899,5900,16500,6),
('HYD','COK',884,95,'{AI,6E}',2199,4500,12800,6),
('HYD','VTZ',347,60,'{AI,6E}',1499,3100,8800,6),
('HYD','BBI',1010,110,'{AI,6E}',2499,5100,14200,4),
('HYD','IXR',1167,125,'{AI,6E}',2699,5500,15200,2),
('HYD','NAG',629,80,'{AI,6E}',1999,4100,11500,4),
-- CCU hub routes
('CCU','GAU',430,65,'{AI,6E,SG}',1699,3500,10000,10),
('CCU','IXB',583,75,'{AI,6E}',1899,3900,11000,4),
('CCU','PAT',513,70,'{AI,6E}',1799,3700,10500,4),
('CCU','BBI',440,65,'{AI,6E}',1599,3300,9400,6),
('CCU','IXR',341,60,'{AI,6E}',1499,3100,8800,4),
('CCU','IMF',1006,110,'{AI,6E}',2499,5100,14200,2),
('CCU','IXA',359,60,'{AI,6E}',1599,3300,9500,4),
-- Northeast routes
('GAU','IMF',499,70,'{AI,6E}',1799,3700,10500,4),
('GAU','IXA',326,55,'{AI,6E}',1499,3100,8800,4),
('GAU','DIB',439,65,'{AI,6E}',1699,3500,9900,4),
('GAU','IXI',287,55,'{AI,6E}',1399,2900,8200,2),
('GAU','SHL',101,35,'{AI}',1299,2700,7700,2),
-- South routes
('COK','TRV',215,45,'{AI,6E,SG}',999,2100,6500,10),
('COK','TRZ',410,60,'{6E,SG}',1399,2900,8300,4),
('COK','IXE',190,40,'{AI,6E}',999,2100,6200,4),
-- West routes
('AMD','JAI',560,70,'{AI,6E}',1799,3700,10500,4),
('AMD','IDR',295,55,'{AI,6E}',1299,2700,7700,2),
('AMD','UDR',241,50,'{AI,6E}',1199,2500,7200,2),
-- Andaman
('IXZ','CCU',1255,135,'{AI,6E}',2899,5900,16500,4),
('IXZ','MAA',1372,145,'{AI}',3099,6300,17500,2)
ON CONFLICT (origin_code,destination_code) DO UPDATE SET
  min_price_inr=EXCLUDED.min_price_inr,
  avg_price_inr=EXCLUDED.avg_price_inr,
  airlines=EXCLUDED.airlines;

-- ============================================================
-- USERS — Extended auth profile
-- ============================================================
CREATE TABLE IF NOT EXISTS public.profiles (
  id                  UUID REFERENCES auth.users(id) ON DELETE CASCADE PRIMARY KEY,
  email               TEXT UNIQUE NOT NULL,
  full_name           TEXT,
  display_name        TEXT,
  phone               TEXT,
  phone_verified      BOOLEAN DEFAULT FALSE,
  email_verified      BOOLEAN DEFAULT FALSE,
  date_of_birth       DATE,
  gender              TEXT CHECK (gender IN ('MALE','FEMALE','OTHER','PREFER_NOT_TO_SAY')),
  nationality         TEXT DEFAULT 'Indian',
  passport_number     TEXT,
  passport_expiry     DATE,
  aadhaar_last4       TEXT,
  preferred_currency  TEXT DEFAULT 'INR',
  preferred_cabin     TEXT DEFAULT 'ECONOMY',
  preferred_language  TEXT DEFAULT 'en',
  avatar_url          TEXT,
  -- Notification preferences
  notify_email        BOOLEAN DEFAULT TRUE,
  notify_sms          BOOLEAN DEFAULT TRUE,
  notify_whatsapp     BOOLEAN DEFAULT FALSE,
  notify_push         BOOLEAN DEFAULT FALSE,
  -- Travel preferences
  preferred_airlines  TEXT[],
  preferred_seats     TEXT DEFAULT 'WINDOW',
  meal_preference     TEXT DEFAULT 'VEG',
  frequent_flyer      JSONB DEFAULT '{}',  -- {airline: ff_number}
  -- Loyalty
  skymind_points      INT DEFAULT 0,
  tier                TEXT DEFAULT 'BLUE' CHECK (tier IN ('BLUE','SILVER','GOLD','PLATINUM')),
  -- Metadata
  last_login          TIMESTAMPTZ,
  login_count         INT DEFAULT 0,
  created_at          TIMESTAMPTZ DEFAULT NOW(),
  updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- USER SESSIONS (for tracking)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.user_sessions (
  id          UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  user_id     UUID REFERENCES profiles(id) ON DELETE CASCADE,
  ip_address  TEXT,
  user_agent  TEXT,
  device_type TEXT,
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  expires_at  TIMESTAMPTZ
);

-- ============================================================
-- FLIGHTS (live/cached flight data)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.flights (
  id               UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  flight_number    TEXT NOT NULL,
  airline_code     TEXT REFERENCES airlines(iata_code),
  origin_code      TEXT REFERENCES airports(iata_code),
  destination_code TEXT REFERENCES airports(iata_code),
  departure_time   TIMESTAMPTZ NOT NULL,
  arrival_time     TIMESTAMPTZ NOT NULL,
  duration_min     INT NOT NULL,
  stops            INT DEFAULT 0,
  cabin_class      TEXT DEFAULT 'ECONOMY',
  aircraft_type    TEXT,
  total_seats      INT DEFAULT 180,
  available_seats  INT,
  status           TEXT DEFAULT 'SCHEDULED' CHECK (status IN ('SCHEDULED','DELAYED','CANCELLED','DEPARTED','ARRIVED')),
  terminal         TEXT,
  gate             TEXT,
  amadeus_offer_id TEXT,
  raw_offer        JSONB,
  created_at       TIMESTAMPTZ DEFAULT NOW(),
  updated_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_flights_route ON flights(origin_code, destination_code);
CREATE INDEX IF NOT EXISTS idx_flights_departure ON flights(departure_time);
CREATE INDEX IF NOT EXISTS idx_flights_airline ON flights(airline_code);

-- ============================================================
-- PRICE HISTORY (ML training data)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.price_history (
  id               UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  origin_code      TEXT REFERENCES airports(iata_code),
  destination_code TEXT REFERENCES airports(iata_code),
  airline_code     TEXT REFERENCES airlines(iata_code),
  cabin_class      TEXT DEFAULT 'ECONOMY',
  price            DECIMAL(10,2) NOT NULL,
  currency         TEXT DEFAULT 'INR',
  departure_date   DATE NOT NULL,
  days_until_dep   INT,
  day_of_week      INT,
  month            INT,
  is_holiday       BOOLEAN DEFAULT FALSE,
  is_long_weekend  BOOLEAN DEFAULT FALSE,
  seats_available  INT,
  load_factor      DECIMAL(5,2),  -- % seats filled
  recorded_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ph_route ON price_history(origin_code, destination_code);
CREATE INDEX IF NOT EXISTS idx_ph_date ON price_history(departure_date);
CREATE INDEX IF NOT EXISTS idx_ph_airline ON price_history(airline_code);

-- ============================================================
-- BOOKINGS
-- ============================================================
CREATE TABLE IF NOT EXISTS public.bookings (
  id                  UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  booking_reference   TEXT UNIQUE NOT NULL,
  user_id             UUID REFERENCES profiles(id),
  flight_id           UUID REFERENCES flights(id),
  amadeus_booking_id  TEXT,
  status              TEXT DEFAULT 'PENDING'
                      CHECK (status IN ('PENDING','CONFIRMED','CANCELLED','REFUNDED','EXPIRED')),
  total_price         DECIMAL(10,2) NOT NULL,
  base_fare           DECIMAL(10,2),
  taxes               DECIMAL(10,2),
  baggage_charges     DECIMAL(10,2) DEFAULT 0,
  meal_charges        DECIMAL(10,2) DEFAULT 0,
  currency            TEXT DEFAULT 'INR',
  cabin_class         TEXT DEFAULT 'ECONOMY',
  payment_status      TEXT DEFAULT 'UNPAID'
                      CHECK (payment_status IN ('UNPAID','PAID','REFUNDED','PARTIALLY_REFUNDED')),
  payment_method      TEXT,
  payment_id          TEXT,
  razorpay_order_id   TEXT,
  razorpay_signature  TEXT,
  -- Notification tracking
  confirmation_sent   BOOLEAN DEFAULT FALSE,
  reminder_sent       BOOLEAN DEFAULT FALSE,
  checkin_notif_sent  BOOLEAN DEFAULT FALSE,
  -- Flight offer snapshot
  flight_offer_data   JSONB,
  contact_email       TEXT,
  contact_phone       TEXT,
  booking_source      TEXT DEFAULT 'WEB',
  coupon_code         TEXT,
  discount_amount     DECIMAL(10,2) DEFAULT 0,
  skymind_points_used INT DEFAULT 0,
  skymind_points_earned INT DEFAULT 0,
  created_at          TIMESTAMPTZ DEFAULT NOW(),
  updated_at          TIMESTAMPTZ DEFAULT NOW(),
  cancelled_at        TIMESTAMPTZ,
  cancellation_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings(user_id);
CREATE INDEX IF NOT EXISTS idx_bookings_ref ON bookings(booking_reference);
CREATE INDEX IF NOT EXISTS idx_bookings_status ON bookings(status);

-- ============================================================
-- PASSENGERS
-- ============================================================
CREATE TABLE IF NOT EXISTS public.passengers (
  id                UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  booking_id        UUID REFERENCES bookings(id) ON DELETE CASCADE,
  type              TEXT DEFAULT 'ADULT' CHECK (type IN ('ADULT','CHILD','INFANT')),
  title             TEXT CHECK (title IN ('MR','MRS','MS','DR','MASTER','MISS')),
  first_name        TEXT NOT NULL,
  last_name         TEXT NOT NULL,
  date_of_birth     DATE,
  gender            TEXT,
  nationality       TEXT,
  passport_number   TEXT,
  passport_expiry   DATE,
  passport_country  TEXT,
  aadhaar_number    TEXT,
  seat_number       TEXT,
  seat_preference   TEXT DEFAULT 'WINDOW',
  meal_preference   TEXT DEFAULT 'VEG',
  baggage_kg        INT DEFAULT 15,
  ssrCodes          TEXT[],  -- special service requests
  ff_number         TEXT,    -- frequent flyer number
  created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_passengers_booking ON passengers(booking_id);

-- ============================================================
-- NOTIFICATIONS — Central notification log
-- ============================================================
CREATE TABLE IF NOT EXISTS public.notifications (
  id            UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  user_id       UUID REFERENCES profiles(id) ON DELETE CASCADE,
  booking_id    UUID REFERENCES bookings(id),
  alert_id      UUID,
  type          TEXT NOT NULL CHECK (type IN (
                  'BOOKING_CONFIRMATION',
                  'PAYMENT_SUCCESS',
                  'PRICE_ALERT',
                  'FLIGHT_REMINDER',
                  'CHECKIN_REMINDER',
                  'FLIGHT_STATUS',
                  'CANCELLATION',
                  'REFUND',
                  'WELCOME',
                  'OTP',
                  'PROMOTIONAL'
                )),
  channel       TEXT NOT NULL CHECK (channel IN ('EMAIL','SMS','WHATSAPP','PUSH')),
  recipient     TEXT NOT NULL,  -- email or phone number
  subject       TEXT,
  message       TEXT NOT NULL,
  template_id   TEXT,
  status        TEXT DEFAULT 'PENDING'
                CHECK (status IN ('PENDING','SENT','DELIVERED','FAILED','BOUNCED')),
  provider      TEXT,   -- 'sendgrid','twilio','firebase'
  provider_id   TEXT,   -- provider's message ID
  error_message TEXT,
  retry_count   INT DEFAULT 0,
  scheduled_at  TIMESTAMPTZ DEFAULT NOW(),
  sent_at       TIMESTAMPTZ,
  delivered_at  TIMESTAMPTZ,
  opened_at     TIMESTAMPTZ,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notif_status ON notifications(status);
CREATE INDEX IF NOT EXISTS idx_notif_scheduled ON notifications(scheduled_at);

-- ============================================================
-- NOTIFICATION TEMPLATES
-- ============================================================
CREATE TABLE IF NOT EXISTS public.notification_templates (
  id          UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  template_id TEXT UNIQUE NOT NULL,
  name        TEXT NOT NULL,
  type        TEXT NOT NULL,
  channel     TEXT NOT NULL,
  subject     TEXT,  -- for email
  body_html   TEXT,  -- for email HTML
  body_text   TEXT,  -- for SMS/WhatsApp plain text
  variables   JSONB, -- {variable_name: description}
  is_active   BOOLEAN DEFAULT TRUE,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Insert default templates
INSERT INTO notification_templates (template_id, name, type, channel, subject, body_html, body_text, variables) VALUES
('booking_confirm_email', 'Booking Confirmation Email', 'BOOKING_CONFIRMATION', 'EMAIL',
 '✈️ Your flight {{booking_ref}} is confirmed! | SkyMind',
 '<h2>Booking Confirmed!</h2><p>Hi {{name}},</p><p>Your booking <strong>{{booking_ref}}</strong> is confirmed.</p><p>Flight: <strong>{{origin}} → {{destination}}</strong></p><p>Date: <strong>{{departure_date}}</strong></p><p>Amount Paid: <strong>₹{{amount}}</strong></p>',
 'Hi {{name}}, your booking {{booking_ref}} is confirmed! Flight: {{origin}} to {{destination}} on {{departure_date}}. Amount: ₹{{amount}}',
 '{"name":"Passenger name","booking_ref":"Booking reference","origin":"Origin IATA","destination":"Dest IATA","departure_date":"Date","amount":"Amount paid"}'::jsonb),
('booking_confirm_sms', 'Booking Confirmation SMS', 'BOOKING_CONFIRMATION', 'SMS',
 NULL,
 NULL,
 'SkyMind: Booking {{booking_ref}} confirmed! {{origin}}→{{destination}} on {{departure_date}}. Amount: ₹{{amount}}. Bon voyage!',
 '{"name":"Name","booking_ref":"Reference","origin":"Origin","destination":"Destination","departure_date":"Date","amount":"Amount"}'::jsonb),
('price_alert_email', 'Price Alert Email', 'PRICE_ALERT', 'EMAIL',
 '🔔 Price Alert: {{origin}} → {{destination}} is now ₹{{current_price}}',
 '<h2>Price Alert Triggered!</h2><p>Hi {{name}},</p><p>Good news! The flight price you''re tracking has dropped.</p><p>Route: <strong>{{origin}} → {{destination}}</strong></p><p>Your Target: <strong>₹{{target_price}}</strong></p><p>Current Price: <strong style="color:green">₹{{current_price}}</strong></p><p>Savings: <strong>₹{{savings}}</strong></p>',
 'SkyMind Alert: {{origin}}→{{destination}} is now ₹{{current_price}} (your target: ₹{{target_price}}). Book now!',
 '{"name":"Name","origin":"Origin","destination":"Destination","target_price":"Target","current_price":"Current price","savings":"Savings"}'::jsonb),
('price_alert_sms', 'Price Alert SMS', 'PRICE_ALERT', 'SMS',
 NULL, NULL,
 'SkyMind Alert! {{origin}}→{{destination}} dropped to ₹{{current_price}} (target ₹{{target_price}}). Book: skymind.app/flights',
 '{"origin":"Origin","destination":"Destination","current_price":"Price","target_price":"Target"}'::jsonb),
('checkin_reminder_email', 'Check-in Reminder', 'CHECKIN_REMINDER', 'EMAIL',
 '⏰ Check-in open for your flight {{flight_number}} tomorrow',
 '<h2>Time to Check In!</h2><p>Hi {{name}},</p><p>Online check-in is now open for your flight <strong>{{flight_number}}</strong>.</p><p>Departure: <strong>{{departure_time}}</strong> from <strong>{{terminal}}</strong></p>',
 'SkyMind: Check-in open for {{flight_number}} on {{departure_date}}. Departure at {{departure_time}}.',
 '{"name":"Name","flight_number":"Flight no","departure_date":"Date","departure_time":"Time","terminal":"Terminal"}'::jsonb),
('welcome_email', 'Welcome Email', 'WELCOME', 'EMAIL',
 '👋 Welcome to SkyMind — Smarter flights await!',
 '<h2>Welcome to SkyMind!</h2><p>Hi {{name}},</p><p>You''ve joined thousands of smart travelers using AI to find the best flight deals.</p><p>Your account is ready. Start searching flights and let our AI predict the best time to book!</p>',
 'Welcome to SkyMind, {{name}}! Your AI-powered flight platform is ready. Start saving on flights at skymind.app',
 '{"name":"User name"}'::jsonb),
('otp_sms', 'OTP SMS', 'OTP', 'SMS',
 NULL, NULL,
 'SkyMind: Your OTP is {{otp}}. Valid for 10 minutes. Do not share this with anyone.',
 '{"otp":"One-time password"}'::jsonb)
ON CONFLICT (template_id) DO NOTHING;

-- ============================================================
-- PRICE ALERTS (enhanced)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.price_alerts (
  id               UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  user_id          UUID REFERENCES profiles(id) ON DELETE CASCADE,
  origin_code      TEXT REFERENCES airports(iata_code),
  destination_code TEXT REFERENCES airports(iata_code),
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
  lowest_seen      DECIMAL(10,2),
  triggered_count  INT DEFAULT 0,
  triggered_at     TIMESTAMPTZ,
  expires_at       TIMESTAMPTZ,
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alerts_user ON price_alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_alerts_active ON price_alerts(is_active) WHERE is_active = TRUE;

-- ============================================================
-- SAVED SEARCHES
-- ============================================================
CREATE TABLE IF NOT EXISTS public.saved_searches (
  id               UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  user_id          UUID REFERENCES profiles(id) ON DELETE CASCADE,
  origin_code      TEXT REFERENCES airports(iata_code),
  destination_code TEXT REFERENCES airports(iata_code),
  departure_date   DATE,
  return_date      DATE,
  adults           INT DEFAULT 1,
  cabin_class      TEXT DEFAULT 'ECONOMY',
  name             TEXT,
  search_params    JSONB,
  last_searched    TIMESTAMPTZ DEFAULT NOW(),
  search_count     INT DEFAULT 1,
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- OTP / PHONE VERIFICATION
-- ============================================================
CREATE TABLE IF NOT EXISTS public.otp_verifications (
  id          UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  user_id     UUID REFERENCES profiles(id) ON DELETE CASCADE,
  phone       TEXT,
  email       TEXT,
  otp_hash    TEXT NOT NULL,
  purpose     TEXT CHECK (purpose IN ('PHONE_VERIFY','EMAIL_VERIFY','LOGIN','RESET_PASSWORD')),
  is_used     BOOLEAN DEFAULT FALSE,
  attempts    INT DEFAULT 0,
  expires_at  TIMESTAMPTZ NOT NULL,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- COUPONS / PROMO CODES
-- ============================================================
CREATE TABLE IF NOT EXISTS public.coupons (
  id              UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  code            TEXT UNIQUE NOT NULL,
  description     TEXT,
  discount_type   TEXT CHECK (discount_type IN ('PERCENT','FLAT')),
  discount_value  DECIMAL(10,2),
  max_discount    DECIMAL(10,2),
  min_booking     DECIMAL(10,2) DEFAULT 0,
  usage_limit     INT,
  used_count      INT DEFAULT 0,
  valid_from      TIMESTAMPTZ DEFAULT NOW(),
  valid_until     TIMESTAMPTZ,
  applicable_on   TEXT[] DEFAULT '{ALL}',
  is_active       BOOLEAN DEFAULT TRUE,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO coupons (code, description, discount_type, discount_value, max_discount, min_booking, usage_limit, valid_until) VALUES
('SKYMIND10', '10% off on first booking', 'PERCENT', 10, 1500, 3000, 1000, NOW() + INTERVAL '1 year'),
('FLAT500', 'Flat ₹500 off', 'FLAT', 500, 500, 2000, 500, NOW() + INTERVAL '6 months'),
('NEWUSER', '15% off for new users', 'PERCENT', 15, 2000, 1000, 999, NOW() + INTERVAL '1 year')
ON CONFLICT (code) DO NOTHING;

-- ============================================================
-- ROW LEVEL SECURITY
-- ============================================================
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.bookings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.passengers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.price_alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.saved_searches ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.otp_verifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.flights ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.price_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.airports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.airlines ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.routes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notification_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coupons ENABLE ROW LEVEL SECURITY;

-- Public read policies
CREATE POLICY "Public read airports" ON airports FOR SELECT USING (true);
CREATE POLICY "Public read airlines" ON airlines FOR SELECT USING (true);
CREATE POLICY "Public read routes" ON routes FOR SELECT USING (true);
CREATE POLICY "Public read flights" ON flights FOR SELECT USING (true);
CREATE POLICY "Public read price_history" ON price_history FOR SELECT USING (true);
CREATE POLICY "Public read templates" ON notification_templates FOR SELECT USING (true);
CREATE POLICY "Public read coupons" ON coupons FOR SELECT USING (is_active = true);

-- User-owned data policies
CREATE POLICY "Users view own profile" ON profiles FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Users update own profile" ON profiles FOR UPDATE USING (auth.uid() = id);
CREATE POLICY "Users insert own profile" ON profiles FOR INSERT WITH CHECK (auth.uid() = id);

CREATE POLICY "Users view own bookings" ON bookings FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users create bookings" ON bookings FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users update own bookings" ON bookings FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users view own passengers" ON passengers FOR SELECT
  USING (booking_id IN (SELECT id FROM bookings WHERE user_id = auth.uid()));
CREATE POLICY "Users insert passengers" ON passengers FOR INSERT
  WITH CHECK (booking_id IN (SELECT id FROM bookings WHERE user_id = auth.uid()));

CREATE POLICY "Users manage own alerts" ON price_alerts FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users manage own searches" ON saved_searches FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users view own notifications" ON notifications FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users view own sessions" ON user_sessions FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users manage own OTP" ON otp_verifications FOR ALL USING (auth.uid() = user_id);

-- ============================================================
-- FUNCTIONS & TRIGGERS
-- ============================================================

-- Auto-create profile on signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
  INSERT INTO public.profiles (id, email, full_name, display_name)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'full_name', split_part(NEW.email, '@', 1)),
    COALESCE(NEW.raw_user_meta_data->>'full_name', split_part(NEW.email, '@', 1))
  );
  -- Queue welcome notification
  INSERT INTO public.notifications (user_id, type, channel, recipient, subject, message, template_id)
  VALUES (
    NEW.id, 'WELCOME', 'EMAIL', NEW.email,
    '👋 Welcome to SkyMind!',
    'Welcome to SkyMind! Your AI-powered flight platform is ready.',
    'welcome_email'
  );
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION public.update_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$;

CREATE TRIGGER trg_profiles_updated_at BEFORE UPDATE ON profiles
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_bookings_updated_at BEFORE UPDATE ON bookings
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_flights_updated_at BEFORE UPDATE ON flights
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Queue booking notifications on confirmation
CREATE OR REPLACE FUNCTION public.handle_booking_confirmed()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
  v_profile profiles%ROWTYPE;
BEGIN
  IF NEW.payment_status = 'PAID' AND OLD.payment_status = 'UNPAID' THEN
    SELECT * INTO v_profile FROM profiles WHERE id = NEW.user_id;
    -- Email notification
    IF v_profile.notify_email THEN
      INSERT INTO notifications (user_id, booking_id, type, channel, recipient, subject, message, template_id)
      VALUES (NEW.user_id, NEW.id, 'BOOKING_CONFIRMATION', 'EMAIL',
        NEW.contact_email,
        '✈️ Booking ' || NEW.booking_reference || ' confirmed! | SkyMind',
        'Your booking ' || NEW.booking_reference || ' is confirmed. Amount: ₹' || NEW.total_price,
        'booking_confirm_email');
    END IF;
    -- SMS notification
    IF v_profile.notify_sms AND NEW.contact_phone IS NOT NULL THEN
      INSERT INTO notifications (user_id, booking_id, type, channel, recipient, message, template_id)
      VALUES (NEW.user_id, NEW.id, 'BOOKING_CONFIRMATION', 'SMS',
        NEW.contact_phone,
        'SkyMind: Booking ' || NEW.booking_reference || ' confirmed! Amount: ₹' || NEW.total_price,
        'booking_confirm_sms');
    END IF;
    -- Award loyalty points (1 point per ₹100)
    UPDATE profiles SET
      skymind_points = skymind_points + FLOOR(NEW.total_price / 100)::INT
    WHERE id = NEW.user_id;
    -- Update booking with points earned
    NEW.skymind_points_earned = FLOOR(NEW.total_price / 100)::INT;
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_booking_confirmed BEFORE UPDATE ON bookings
  FOR EACH ROW EXECUTE FUNCTION handle_booking_confirmed();

-- ============================================================
-- USEFUL VIEWS
-- ============================================================

-- Full booking details view
CREATE OR REPLACE VIEW v_booking_details AS
SELECT
  b.id, b.booking_reference, b.status, b.payment_status,
  b.total_price, b.currency, b.cabin_class,
  b.contact_email, b.contact_phone, b.created_at,
  p.full_name AS user_name, p.email AS user_email, p.phone AS user_phone,
  p.notify_email, p.notify_sms,
  ao.city AS origin_city, ao.name AS origin_airport, ao.iata_code AS origin_code,
  ad.city AS dest_city, ad.name AS dest_airport, ad.iata_code AS dest_code,
  b.flight_offer_data
FROM bookings b
JOIN profiles p ON b.user_id = p.id
LEFT JOIN flights f ON b.flight_id = f.id
LEFT JOIN airports ao ON f.origin_code = ao.iata_code
LEFT JOIN airports ad ON f.destination_code = ad.iata_code;

-- Pending notifications view (for backend cron)
CREATE OR REPLACE VIEW v_pending_notifications AS
SELECT * FROM notifications
WHERE status = 'PENDING' AND scheduled_at <= NOW()
ORDER BY scheduled_at ASC
LIMIT 100;

-- Active price alerts with current prices
CREATE OR REPLACE VIEW v_active_alerts AS
SELECT
  pa.*,
  p.full_name, p.email, p.phone,
  p.notify_email, p.notify_sms, p.notify_whatsapp,
  ao.city AS origin_city,
  ad.city AS dest_city
FROM price_alerts pa
JOIN profiles p ON pa.user_id = p.id
JOIN airports ao ON pa.origin_code = ao.iata_code
JOIN airports ad ON pa.destination_code = ad.iata_code
WHERE pa.is_active = TRUE
  AND (pa.expires_at IS NULL OR pa.expires_at > NOW());

-- All domestic routes with airport details
CREATE OR REPLACE VIEW v_domestic_routes AS
SELECT
  r.origin_code, ao.city AS origin_city, ao.name AS origin_airport,
  ao.state AS origin_state,
  r.destination_code, ad.city AS dest_city, ad.name AS dest_airport,
  ad.state AS dest_state,
  r.distance_km, r.avg_duration_min, r.airlines,
  r.min_price_inr, r.avg_price_inr, r.flights_per_day
FROM routes r
JOIN airports ao ON r.origin_code = ao.iata_code
JOIN airports ad ON r.destination_code = ad.iata_code
WHERE ao.country_code = 'IN' AND ad.country_code = 'IN'
ORDER BY r.flights_per_day DESC;

