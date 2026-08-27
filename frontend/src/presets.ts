export interface DopMasterPreset {
  name: string;
  tagline: string;
  description: string;
  focal_length: number;
  lens_type: string;
  aperture: string;
  sensor_format: string;
  camera_body: string;
  lighting_style: string;
  lighting_ratio: string;
  color_temperature_k: number;
  color_palette: string;
  lut_emulation: string;
  prompt_style_tag: string;
  category?: 'naturalist' | 'noir' | 'anamorphic' | 'stylized' | 'large-format' | 'vintage';
}

export const DEFAULT_DOP_PRESETS: Record<string, DopMasterPreset> = {
  "Roger Deakins": {
    name: "Roger Deakins (Natural Motivated)",
    tagline: "Organic Motivated Light & Spherical Mastery",
    description: "Characterized by practical source lighting, clean spherical Arri Master Primes, deep organic shadow details, and patient camera framing (Blade Runner 2049, 1917, Sicario).",
    focal_length: 35,
    lens_type: "Spherical Prime (ARRI Master Prime)",
    aperture: "T2.8",
    sensor_format: "Large Format 35mm (ARRI ALEXA Mini LF)",
    camera_body: "ARRI ALEXA Mini LF",
    lighting_style: "Natural Motivated Diffused",
    lighting_ratio: "4:1 (Organic Depth)",
    color_temperature_k: 5600,
    color_palette: "Earthy ochres, deep stone greys, golden motivated sunlight shafts",
    lut_emulation: "Kodak 5219 Vision3 500T",
    prompt_style_tag: "cinematic still in the style of Roger Deakins, natural motivated lighting, volumetric daylight, master prime clarity, 35mm lens, 2.39:1 scope, 8k photorealistic film still",
    category: "naturalist"
  },
  "David Fincher": {
    name: "David Fincher / Jeff Cronenweth (Low-Key Neo-Noir)",
    tagline: "Clinical Precision, Cold Low-Key Chiaroscuro",
    description: "Controlled studio environments, deep contrast ratios, subtle greenish-amber undertones, locked-off or fluid tracking, and razor-sharp digital sensors (Fight Club, The Social Network, Gone Girl).",
    focal_length: 28,
    lens_type: "Leica Summilux-C",
    aperture: "T2.0",
    sensor_format: "RED V-Raptor 8K VV",
    camera_body: "RED V-Raptor 8K",
    lighting_style: "Low-Key Chiaroscuro Noir",
    lighting_ratio: "8:1 (Deep Contrast)",
    color_temperature_k: 4300,
    color_palette: "Desaturated teal, olive green, warm tungsten edge light against pitch blacks",
    lut_emulation: "Bleach Bypass Custom LUT",
    prompt_style_tag: "cinematic film still in the style of David Fincher, low-key lighting, deep shadows, controlled amber and green undertones, 28mm wide angle, neo-noir atmosphere, ultra-sharp 8k film capture",
    category: "noir"
  },
  "Greig Fraser": {
    name: "Greig Fraser (Soft Atmospheric Anamorphic)",
    tagline: "Tactile Texture, Heavy Silhouettes & Haze",
    description: "Tactile cinematic atmosphere with soft high contrast, anamorphic oval bokeh, volumetric haze, atmospheric smoke, and bold expressive silhouettes (Dune, The Batman, Rogue One).",
    focal_length: 40,
    lens_type: "Anamorphic 2x (Atlas Orion / Panavision C-Series)",
    aperture: "T1.8",
    sensor_format: "Full Frame 65mm (ARRI ALEXA 65)",
    camera_body: "ARRI ALEXA 65",
    lighting_style: "Atmospheric Backlit Silhouette",
    lighting_ratio: "6:1 (Soft Heavy Contrast)",
    color_temperature_k: 3200,
    color_palette: "Monochromatic amber, heavy charcoal shadows, saturated sodium-vapor practicals",
    lut_emulation: "Film Print Kodak 2383",
    prompt_style_tag: "cinematic film still in the style of Greig Fraser, atmospheric haze, heavy silhouette lighting, soft 2x anamorphic lens flare, deep tactile texture, 2.39:1 anamorphic scope, 8k masterpiece",
    category: "anamorphic"
  },
  "Gordon Willis": {
    name: "Gordon Willis (Prince of Shadows)",
    tagline: "Top-Lit Practicals & Underexposed Warmth",
    description: "Bold underexposure, top-lit amber practical lamps, warm Rembrandt lighting, and dignified classical staging (The Godfather, Manhattan, Klute).",
    focal_length: 50,
    lens_type: "Vintage Super Baltar",
    aperture: "T2.8",
    sensor_format: "Super 35mm (Panavision Panaflex Gold)",
    camera_body: "Panavision Panaflex Gold II (35mm)",
    lighting_style: "Top-Lit Rembrandt Chiaroscuro",
    lighting_ratio: "16:1 (Extreme Low-Key)",
    color_temperature_k: 3000,
    color_palette: "Deep sepia, dark espresso shadows, warm golden skin highlights",
    lut_emulation: "Kodak 5254 35mm Vintage",
    prompt_style_tag: "cinematic still in the style of Gordon Willis, top-lit warm practical light, underexposed rich dark shadows, classic 35mm film grain, 50mm vintage lens perspective, dramatic portrait",
    category: "vintage"
  },
  "Emmanuel Lubezki": {
    name: "Emmanuel Lubezki (Fluid Naturalist)",
    tagline: "Ultra-Wide Natural Light & Continuous Motion",
    description: "Expansive ultra-wide lenses (14mm-24mm) positioned close to actors, natural golden hour sky light, and long continuous fluid Steadicam/Gimbal movements (The Revenant, Birdman, Children of Men).",
    focal_length: 21,
    lens_type: "Master Prime Ultra-Wide",
    aperture: "T1.4",
    sensor_format: "Large Format 35mm (ARRI ALEXA Mini LF)",
    camera_body: "ARRI ALEXA Mini LF",
    lighting_style: "Available Golden Hour Natural",
    lighting_ratio: "2:1 (Gentle Wrap)",
    color_temperature_k: 6000,
    color_palette: "Vibrant natural greens, azure blue skies, luminous golden backlight",
    lut_emulation: "Arri LogC4 Naturalist",
    prompt_style_tag: "cinematic still in the style of Emmanuel Lubezki, ultra-wide 21mm lens perspective close to subject, magical golden hour natural light, expansive sky, fluid motion feel, 8k photorealistic",
    category: "naturalist"
  },
  "Wes Anderson": {
    name: "Wes Anderson / Robert Yeoman (Symmetrical Pastel)",
    tagline: "Symmetrical 1-Point Perspective & Pastel Palette",
    description: "Obsessive planar symmetry, flat high-key fill lighting, whimsical pastel color schemes, and crisp deep-focus theatrical framing (The Grand Budapest Hotel, Asteroid City, Moonrise Kingdom).",
    focal_length: 40,
    lens_type: "Anamorphic Primo (Symmetrical)",
    aperture: "T5.6",
    sensor_format: "Super 35 3-Perf (Arricam ST)",
    camera_body: "Arricam ST 35mm",
    lighting_style: "High-Key Evenly Diffused Studio",
    lighting_ratio: "1.5:1 (Flat Bright)",
    color_temperature_k: 5000,
    color_palette: "Mustard yellow, pastel pink, soft mint green, symmetrical saturated warmth",
    lut_emulation: "Fujifilm Eterna 250D",
    prompt_style_tag: "cinematic still in the style of Wes Anderson, perfectly symmetrical composition, pastel color palette, soft flat high-key lighting, whimsical retro details, 2.39:1 scope, 8k crisp film capture",
    category: "stylized"
  },
  "Hoyte van Hoytema": {
    name: "Hoyte van Hoytema (Large Format IMAX Realism)",
    tagline: "Monumental IMAX Scale, Tactile Skin & Deep Contrast",
    description: "Monumental large-format 65mm/70mm IMAX resolution, deep natural contrast, candid micro-details on skin, and grand authentic practical environments (Oppenheimer, Interstellar, Dunkirk, Nope).",
    focal_length: 50,
    lens_type: "Hasselblad 65mm / Panavision Spherical",
    aperture: "T2.0",
    sensor_format: "IMAX 70mm 15-Perf (IMAX MKIV)",
    camera_body: "IMAX MKIV 15-Perf 65mm",
    lighting_style: "Natural Hard Direct & Deep Cold Shadows",
    lighting_ratio: "5:1 (Crisp Naturalist)",
    color_temperature_k: 5200,
    color_palette: "Steely blues, deep obsidian blacks, textured flesh tones, stark daylight",
    lut_emulation: "Kodak Vision3 250D 5207",
    prompt_style_tag: "cinematic IMAX still in the style of Hoyte van Hoytema, 70mm large format detail, razor-sharp textures, authentic natural hard lighting, crisp deep shadows, Oppenheimer aesthetic, 8k",
    category: "large-format"
  },
  "Robert Richardson": {
    name: "Robert Richardson (Halation Overexposure)",
    tagline: "Signature Overhead Blown Highlights & Warm Halation",
    description: "Blinding overhead rim lighting, intentionally clipped white hotspots on actors' hair and shoulders, warm diffusion filters, and rich saturated color (Inglourious Basterds, Kill Bill, Casino, Once Upon a Time in Hollywood).",
    focal_length: 35,
    lens_type: "Panavision Ultra Panatar Anamorphic",
    aperture: "T2.8",
    sensor_format: "Super 35mm (Panavision Panaflex Gold)",
    camera_body: "Panavision Panaflex Millennium XL2",
    lighting_style: "Overhead Hard Hotspot Key & High Halation",
    lighting_ratio: "8:1 (Blown Top Rim)",
    color_temperature_k: 4500,
    color_palette: "Warm golden glows, intense glowing white highlights, rich crimson and brass",
    lut_emulation: "Kodak 5219 Vision3 500T",
    prompt_style_tag: "cinematic still in the style of Robert Richardson, blinding overhead rim light, blown highlight glow, warm halation, Quentin Tarantino cinema aesthetic, rich saturation, 8k film capture",
    category: "stylized"
  },
  "Christopher Doyle": {
    name: "Christopher Doyle / Wong Kar-wai (Neon Step-Print)",
    tagline: "Impressionistic Neon, Step-Printing & Fluid Smear",
    description: "Dreamlike low-shutter motion blur, saturated emerald green and sodium amber neon, intimate wide angles in tight claustrophobic urban spaces (In the Mood for Love, Chungking Express, Fallen Angels).",
    focal_length: 24,
    lens_type: "Cooke S4 / Zeiss Super Speed",
    aperture: "T1.4",
    sensor_format: "Super 35mm (Panavision Panaflex Gold)",
    camera_body: "Arriflex 535B 35mm",
    lighting_style: "Low-Key Neon Practical & Colored Gels",
    lighting_ratio: "10:1 (Moody Saturated Neon)",
    color_temperature_k: 3800,
    color_palette: "Lush jade greens, vivid neon magenta, dirty amber tungsten, smoky shadows",
    lut_emulation: "Fujifilm Reala 500D",
    prompt_style_tag: "cinematic film still in the style of Christopher Doyle and Wong Kar-wai, step-printed motion texture, vivid green and amber neon lights, intimate 24mm wide angle, Hong Kong cinema poetry, 8k",
    category: "stylized"
  },
  "Janusz Kamiński": {
    name: "Janusz Kamiński (Bleach-Bypass Silver Beams)",
    tagline: "90-Degree Shutter, Silver Bleach-Bypass & Light Beams",
    description: "High shutter angle (45°-90°) staccato motion, intense volumetric sunbeams cutting through haze, silvery desaturated skin tones, and expressive streak flares (Saving Private Ryan, Minority Report, Schindler's List).",
    focal_length: 28,
    lens_type: "Panavision C-Series Anamorphic",
    aperture: "T2.0",
    sensor_format: "Super 35mm (Panavision Panaflex Gold)",
    camera_body: "Panavision Platinum 35mm",
    lighting_style: "Harsh Backlit Volumetric Light Beams",
    lighting_ratio: "12:1 (Silver Chiaroscuro)",
    color_temperature_k: 6200,
    color_palette: "Desaturated silver, icy blue highlights, gritty charcoal blacks, piercing white shafts",
    lut_emulation: "Bleach Bypass Custom LUT",
    prompt_style_tag: "cinematic film still in the style of Janusz Kamiński, sharp light beams piercing atmospheric dust, bleach bypass silvery tone, high contrast backlit silhouette, Spielbergian cinematography, 8k",
    category: "noir"
  },
  "Bradford Young": {
    name: "Bradford Young (Tactile Underexposure)",
    tagline: "Deep Charcoal Shadows & Warm Ambient Wrap",
    description: "Subtle deep underexposure, rich velvety black skin tones preserved in soft ambient light, wide open vintage glass, and atmospheric contemplative stillness (Arrival, Selma, Solo: A Star Wars Story).",
    focal_length: 35,
    lens_type: "Vintage Kowa Prominar Anamorphic",
    aperture: "T1.4",
    sensor_format: "Large Format 35mm (ARRI ALEXA Mini LF)",
    camera_body: "ARRI ALEXA Mini LF",
    lighting_style: "Soft Ambient Bounce & Intentional Underexposure",
    lighting_ratio: "8:1 (Velvety Low-Key)",
    color_temperature_k: 3400,
    color_palette: "Warm amber skin glow, espresso and slate undertones, muted organic earth",
    lut_emulation: "Kodak 5219 Vision3 500T",
    prompt_style_tag: "cinematic film still in the style of Bradford Young, rich underexposed shadow detail, soft warm ambient light wrap, shallow depth of field, Arrival atmosphere, 8k tactile film still",
    category: "naturalist"
  },
  "Stanley Kubrick": {
    name: "Stanley Kubrick / John Alcott (Candlelight & Symmetry)",
    tagline: "One-Point Symmetry, Deep Perspective & Candlelight f/0.7",
    description: "Immaculate one-point vanishing perspective, ultra-fast custom NASA lenses shooting in pure authentic candlelight, and deep theatrical compositions (Barry Lyndon, The Shining, 2001: A Space Odyssey).",
    focal_length: 50,
    lens_type: "Carl Zeiss Planar 50mm f/0.7 (NASA Glass)",
    aperture: "T1.3",
    sensor_format: "Super 35mm (Panavision Panaflex Gold)",
    camera_body: "Mitchell BNC Modified (35mm)",
    lighting_style: "Pure Motivated Candlelight & Symmetrical Window Daylight",
    lighting_ratio: "3:1 (Classical Renaissance Balance)",
    color_temperature_k: 2800,
    color_palette: "Warm flickering candle amber, pristine period oils, symmetrical architectural grandeur",
    lut_emulation: "Kodak 5254 35mm Vintage",
    prompt_style_tag: "cinematic still in the style of Stanley Kubrick and John Alcott, perfect one-point perspective symmetry, authentic candlelight illumination, Barry Lyndon painting aesthetic, 8k masterpiece",
    category: "vintage"
  }
};
