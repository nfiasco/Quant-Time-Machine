import type { SVGProps } from "react";
import {
  ArrowRightIcon,
  ArrowUpRightIcon,
  PlayIcon,
  HistoryIcon,
  LayersIcon,
  ChartLineIcon,
  CheckIcon,
  Code2Icon,
} from "lucide-react";
import { Brand as AppBrand } from "@/components/layout/brand";

type IconName =
  | "arrow"
  | "diagonal"
  | "play"
  | "clock"
  | "layers"
  | "chart"
  | "check"
  | "github";
const icons = {
  arrow: ArrowRightIcon,
  diagonal: ArrowUpRightIcon,
  play: PlayIcon,
  clock: HistoryIcon,
  layers: LayersIcon,
  chart: ChartLineIcon,
  check: CheckIcon,
  github: Code2Icon,
};

export function Icon({
  name,
  ...props
}: SVGProps<SVGSVGElement> & { name: IconName }) {
  const Component = icons[name];
  return <Component aria-hidden="true" {...props} />;
}

export function Brand() {
  return (
    <a className="brand" href="#top" aria-label="Quant Time Machine home">
      <AppBrand className="brand-content" />
    </a>
  );
}
