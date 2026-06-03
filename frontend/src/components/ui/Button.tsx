import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "ghost" | "subtle" | "danger";
type Size = "sm" | "md";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-accent text-accent-foreground shadow-sm hover:brightness-110 disabled:bg-accent/40",
  ghost:
    "border border-border text-foreground hover:bg-surface-muted disabled:opacity-40",
  subtle:
    "text-muted hover:bg-surface-muted hover:text-foreground disabled:opacity-40",
  danger:
    "border border-transparent text-danger hover:bg-danger hover:text-white disabled:opacity-40",
};

const SIZES: Record<Size, string> = {
  sm: "text-xs px-2.5 py-1 rounded-md",
  md: "text-sm px-4 py-2 rounded-lg",
};

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
};

export default function Button({
  variant = "primary",
  size = "md",
  className = "",
  ...rest
}: Props) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-1.5 font-medium transition focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 disabled:cursor-not-allowed ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      {...rest}
    />
  );
}
