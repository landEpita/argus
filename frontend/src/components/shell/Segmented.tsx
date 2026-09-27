import type { ReactNode } from "react";

/** A labelled group of toggle buttons: a real fieldset, so the label is announced. */
export function Segmented({
  label,
  small,
  children,
}: {
  label: string;
  small?: boolean;
  children: ReactNode;
}) {
  return (
    <fieldset className={small ? "segmented segmented-s" : "segmented"}>
      <legend className="sr-only">{label}</legend>
      {children}
    </fieldset>
  );
}
