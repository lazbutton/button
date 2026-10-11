import { Select } from "@radix-ui/themes";
import type { ReactNode } from "react";

export function FormField({
  label,
  hint,
  error,
  children,
  htmlFor,
}: {
  label: string;
  hint?: ReactNode;
  error?: ReactNode;
  children: ReactNode;
  htmlFor?: string;
}) {
  return (
    <label className="ui-field" htmlFor={htmlFor}>
      <span className="ui-field-label">{label}</span>
      {children}
      {error ? <span className="ui-field-error">{error}</span> : null}
      {!error && hint ? <span className="ui-field-hint">{hint}</span> : null}
    </label>
  );
}

export type SelectOption = {
  value: string;
  label: string;
  disabled?: boolean;
};

export function SelectField({
  label,
  value,
  options,
  onValueChange,
  hint,
  placeholder,
  disabled,
}: {
  label: string;
  value: string;
  options: SelectOption[];
  onValueChange: (value: string) => void;
  hint?: ReactNode;
  placeholder?: string;
  disabled?: boolean;
}) {
  return (
    <FormField label={label} hint={hint}>
      <Select.Root value={value} onValueChange={onValueChange} disabled={disabled}>
        <Select.Trigger className="ui-field-control" placeholder={placeholder} />
        <Select.Content position="popper">
          {options.map((option) => (
            <Select.Item
              key={option.value}
              value={option.value}
              disabled={option.disabled}
            >
              {option.label}
            </Select.Item>
          ))}
        </Select.Content>
      </Select.Root>
    </FormField>
  );
}
