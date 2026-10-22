import { useEffect, useMemo, useRef } from "react";
import { Animated, Dimensions, Easing, StyleSheet, View } from "react-native";

/**
 * The Poe family, flying across the screen when the brand mark is tapped.
 *
 * Completely useless, and worth having anyway — the same wager the promo
 * site's flock makes, with the same sprite and the same undulating crossing.
 * This app is going to be handed to a dozen volunteers doing unpaid work for
 * somebody else's research, and the difference between a tool people use and
 * one they enjoy using is made of things exactly this size.
 *
 * The promo birds amble across in 17–31 seconds because they are weather; a
 * flock summoned by a tap has to be an answer to it, so these cross in a few.
 * Five birds at the family's relative sizes — parents largest, the yearling
 * between, the fledglings smallest.
 */

const SPRITE = require("../../../assets/crow-flight.png");
/** Ten frames, registered on the beak so only the wings move. */
const FRAMES = 10;
/** One frame of the strip is 190 × 263. */
const FRAME_ASPECT = 190 / 263;
/** Sine samples for the crossing; enough that the curve reads as a curve. */
const SAMPLES = 24;

const between = (lo: number, hi: number) => lo + Math.random() * (hi - lo);

/** Thrasher, Ripjaw, Edgar, and the two fledglings, by relative wingspan. */
const FAMILY_SIZES = [1, 1, 0.88, 0.78, 0.78];

function Bird({ size, onDone }: { size: number; onDone: () => void }) {
  const window = Dimensions.get("window");

  const plan = useMemo(() => {
    const width = 44 * size;
    return {
      width,
      height: width / FRAME_ASPECT,
      duration: between(3600, 6400),
      delay: between(0, 900),
      amplitude: between(8, 30),
      waves: between(1.5, 3),
      phase: Math.random() * Math.PI * 2,
      drift: between(-30, 30),
      top: between(60, window.height * 0.35),
      flap: between(550, 800),
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const progress = useRef(new Animated.Value(0)).current;
  const beat = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const flap = Animated.loop(
      Animated.timing(beat, {
        toValue: 1,
        duration: plan.flap,
        easing: Easing.linear,
        useNativeDriver: true,
      }),
    );
    const flight = Animated.timing(progress, {
      toValue: 1,
      duration: plan.duration,
      delay: plan.delay,
      easing: Easing.linear,
      useNativeDriver: true,
    });
    flap.start();
    flight.start(({ finished }) => {
      flap.stop();
      if (finished) onDone();
    });
    return () => {
      flap.stop();
      flight.stop();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const crossX = progress.interpolate({
    inputRange: [0, 1],
    outputRange: [-plan.width - 20, window.width + 20],
  });

  // The crossing rises and falls with a sine sampled into stops, with a drift
  // so the bird does not arrive at the height it left — a straight line reads
  // as a sprite being slid across.
  const sineStops = Array.from({ length: SAMPLES + 1 }, (_, i) => i / SAMPLES);
  const bobY = progress.interpolate({
    inputRange: sineStops,
    outputRange: sineStops.map(
      (t) =>
        Math.sin(plan.phase + t * plan.waves * Math.PI * 2) * plan.amplitude +
        plan.drift * t,
    ),
  });

  // The wingbeat steps the strip one whole frame at a time: a smooth slide
  // would smear one bird's tail onto the next one's head. Duplicated input
  // stops make the interpolation a staircase.
  const stepIn: number[] = [0];
  const stepOut: number[] = [0];
  for (let frame = 1; frame < FRAMES; frame++) {
    const t = frame / FRAMES;
    stepIn.push(t, t);
    stepOut.push(-(frame - 1) * plan.width, -frame * plan.width);
  }
  stepIn.push(1);
  stepOut.push(-(FRAMES - 1) * plan.width);
  const frameShift = beat.interpolate({ inputRange: stepIn, outputRange: stepOut });

  return (
    <Animated.View
      style={{
        position: "absolute",
        top: plan.top,
        left: 0,
        width: plan.width,
        height: plan.height,
        overflow: "hidden",
        transform: [{ translateX: crossX }, { translateY: bobY }],
      }}
    >
      <Animated.Image
        source={SPRITE}
        resizeMode="stretch"
        style={{
          width: plan.width * FRAMES,
          height: plan.height,
          transform: [{ translateX: frameShift }],
        }}
      />
    </Animated.View>
  );
}

export function Flock({ onDone }: { onDone: () => void }) {
  const remaining = useRef(FAMILY_SIZES.length);
  const landed = () => {
    remaining.current -= 1;
    if (remaining.current === 0) onDone();
  };
  return (
    // Over the list, never in its way: the flock takes no touches.
    <View style={StyleSheet.absoluteFill} pointerEvents="none">
      {FAMILY_SIZES.map((size, index) => (
        <Bird key={index} size={size} onDone={landed} />
      ))}
    </View>
  );
}
