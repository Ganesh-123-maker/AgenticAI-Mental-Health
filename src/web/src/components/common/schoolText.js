const SCHOOL_DISPLAY_NAME_MAP = {
  behavioral: "Behavior Therapy (BT)",
  cbt: "Cognitive Behavioral Therapy (CBT)",
  humanistic: "Humanistic-Existential Therapy (HET)",
  psychodynamic: "Psychodynamic Therapy (PDT)",
  postmodern: "Postmodern Therapy (PMT)",
};

export function getSchoolDisplayName(school) {
  if (!school) return "Not Selected";
  const mapped = SCHOOL_DISPLAY_NAME_MAP[school.id];
  if (mapped) return mapped;
  return school.name || "Not Selected";
}
