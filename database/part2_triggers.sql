-- ============================================================
-- SkyMind PART 2 — Triggers & Functions
-- Run this AFTER part1_tables.sql succeeds
-- ============================================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION public.update_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_profiles_updated_at
  BEFORE UPDATE ON public.profiles
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

CREATE TRIGGER trg_bookings_updated_at
  BEFORE UPDATE ON public.bookings
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

CREATE TRIGGER trg_flights_updated_at
  BEFORE UPDATE ON public.flights
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

-- Auto-create profile when user signs up in Supabase Auth
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  INSERT INTO public.profiles (id, email, full_name, display_name)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'full_name', split_part(NEW.email,'@',1)),
    COALESCE(NEW.raw_user_meta_data->>'full_name', split_part(NEW.email,'@',1))
  )
  ON CONFLICT (id) DO NOTHING;

  INSERT INTO public.notifications (user_id, type, channel, recipient, subject, message)
  VALUES (
    NEW.id, 'WELCOME', 'EMAIL', NEW.email,
    'Welcome to SkyMind!',
    'Welcome! Your AI-powered flight platform is ready.'
  );
  RETURN NEW;
END;
$$;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Queue notifications + award points when payment confirmed
CREATE OR REPLACE FUNCTION public.handle_booking_confirmed()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
  v_profile public.profiles%ROWTYPE;
BEGIN
  IF NEW.payment_status = 'PAID' AND OLD.payment_status <> 'PAID' THEN
    SELECT * INTO v_profile FROM public.profiles WHERE id = NEW.user_id;

    IF v_profile.notify_email AND NEW.contact_email IS NOT NULL THEN
      INSERT INTO public.notifications
        (user_id, booking_id, type, channel, recipient, subject, message)
      VALUES (
        NEW.user_id, NEW.id, 'BOOKING_CONFIRMATION', 'EMAIL', NEW.contact_email,
        'Booking ' || NEW.booking_reference || ' Confirmed!',
        'Your booking is confirmed. Amount: Rs.' || NEW.total_price
      );
    END IF;

    IF v_profile.notify_sms AND NEW.contact_phone IS NOT NULL THEN
      INSERT INTO public.notifications
        (user_id, booking_id, type, channel, recipient, message)
      VALUES (
        NEW.user_id, NEW.id, 'BOOKING_CONFIRMATION', 'SMS', NEW.contact_phone,
        'SkyMind: Booking ' || NEW.booking_reference || ' confirmed! Rs.' || NEW.total_price
      );
    END IF;

    -- Award 1 point per Rs.100 spent
    UPDATE public.profiles
    SET skymind_points = skymind_points + FLOOR(NEW.total_price / 100)::INT
    WHERE id = NEW.user_id;

    NEW.skymind_points_earned := FLOOR(NEW.total_price / 100)::INT;
    NEW.status := 'CONFIRMED';
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_booking_confirmed
  BEFORE UPDATE ON public.bookings
  FOR EACH ROW EXECUTE FUNCTION public.handle_booking_confirmed();

SELECT 'Part 2 complete — triggers and functions installed!' AS status;
