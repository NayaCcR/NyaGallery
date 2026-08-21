"use client";

import { Slot } from "@/components/ui/slot";
import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type Variant = "default" | "secondary" | "outline" | "ghost" | "destructive" | "link";
type Size = "sm" | "md" | "lg" | "icon";

const VARIANT: Record<Variant, string> = {
  default:
    "button-glow-primary bg-primary text-primary-foreground hover:-translate-y-px hover:bg-primary/90 shadow-sm",
  secondary:
    "button-glow-secondary bg-secondary text-secondary-foreground hover:-translate-y-px hover:bg-secondary/80",
  outline:
    "button-glow-secondary border border-input bg-transparent hover:-translate-y-px hover:bg-accent hover:text-accent-foreground",
  ghost: "control-glow hover:bg-accent hover:text-accent-foreground",
  destructive:
    "bg-destructive text-destructive-foreground hover:bg-destructive/90 shadow-sm",
  link: "text-primary underline-offset-4 hover:underline",
};

const SIZE: Record<Size, string> = {
  sm: "h-8 px-3 text-sm rounded-lg",
  md: "h-9 px-4 text-sm rounded-lg",
  lg: "h-10 px-5 text-sm rounded-lg",
  icon: "h-9 w-9 rounded-lg",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  asChild?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", size = "md", asChild, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        ref={ref as never}
        className={cn(
    "inline-flex items-center justify-center gap-2 whitespace-nowrap font-medium transition-[background-color,border-color,box-shadow,transform,color] focus-ring disabled:pointer-events-none disabled:opacity-50",
          VARIANT[variant],
          SIZE[size],
          className
        )}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";
