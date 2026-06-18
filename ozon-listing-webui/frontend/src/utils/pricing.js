import { OZON_REALFBS_DATA } from './pricingData.js'

const RUB_TIERS = [1500, 5000];

export function parseRate(rateText) {
  const text = String(rateText || "")
    .replace(/￥/g, "¥")
    .replace(/,/g, ".")
    .replace(/¥\s*\./g, "¥0.")
    .replace(/\s+/g, " ");
  const match = text.match(/¥\s*([\d.]+)\s*\+\s*¥\s*([\d.]+)\s*\/\s*1\s*[gг克]/i);
  if (!match) return null;
  const parseOzonDecimal = (value) => {
    const parts = String(value).split(".").filter(Boolean);
    if (parts.length <= 1) return Number(value);
    if (parts[0] === "0") {
      const decimals = parts[1] === "0" ? parts.slice(2) : parts.slice(1);
      return Number(`0.${decimals.join("")}`);
    }
    return Number(`${parts[0]}.${parts.slice(1).join("")}`);
  };
  return {
    baseCny: parseOzonDecimal(match[1]),
    perGCny: parseOzonDecimal(match[2]),
  };
}

export function parseRange(rangeText) {
  const nums = String(rangeText || "").match(/\d+(?:[ .]\d+)*/g);
  if (!nums || nums.length < 2) return [null, null];
  return nums.slice(0, 2).map((value) => Number(value.replace(/\s/g, "")));
}

export function chargeableWeight(input) {
  const physical = Number(input.weightG) || 0;
  const length = Number(input.lengthCm) || 0;
  const width = Number(input.widthCm) || 0;
  const height = Number(input.heightCm) || 0;
  const volumeWeight = length && width && height ? (length * width * height) / 6 : 0;
  return {
    physical,
    volumeWeight,
    billable: Math.max(physical, volumeWeight),
  };
}

export function routeBillableWeight(route, input) {
  const physical = Number(input.weightG) || 0;
  const length = Number(input.lengthCm) || 0;
  const width = Number(input.widthCm) || 0;
  const height = Number(input.heightCm) || 0;
  const usesVolume = /volume|max weight/i.test(String(route.tarification || ""));
  if (!usesVolume || !length || !width || !height) {
    return { physical, volumeWeight: 0, billable: physical };
  }
  const divisorMatch = String(route.volumeFormula || "").match(/÷\s*([\d\s]+)/);
  const divisor = divisorMatch ? Number(divisorMatch[1].replace(/\s/g, "")) : 12000;
  const volumeWeight = divisor ? (length * width * height * 1000) / divisor : 0;
  return { physical, volumeWeight, billable: Math.max(physical, volumeWeight) };
}

export function dimensionsPass(route, input) {
  const text = String(route.measurements || "");
  const sides = [Number(input.lengthCm) || 0, Number(input.widthCm) || 0, Number(input.heightCm) || 0];
  if (!sides.some(Boolean)) return true;
  const sum = sides.reduce((a, b) => a + b, 0);
  const longest = Math.max(...sides);
  const sumMatch = text.match(/sum of sides\s*[≤<=]+\s*(\d+)/i);
  const lengthMatch = text.match(/length\s*[≤<=]+\s*(\d+)/i);
  if (sumMatch && sum > Number(sumMatch[1])) return false;
  if (lengthMatch && longest > Number(lengthMatch[1])) return false;
  return true;
}

export function routeStatus(route, input, priceRub) {
  const reasons = [];
  const weight = routeBillableWeight(route, input).billable;
  const minW = Number(route.weightMinG) || 0;
  const maxW = Number(route.weightMaxG) || Infinity;
  const [minRub, maxRub] = parseRange(route.valueRangeRub);

  if (weight < minW || weight > maxW) reasons.push(`weight ${Math.round(weight)}g outside ${minW}-${maxW}g`);
  if (minRub !== null && maxRub !== null && (priceRub < minRub || priceRub > maxRub)) {
    reasons.push(`RUB price outside ${minRub}-${maxRub}`);
  }
  if (input.hasBattery && /forbidden|запрещено|禁止/i.test(String(route.batteries || ""))) reasons.push("battery forbidden");
  if (input.isLiquid && /forbidden|запрещено|禁止/i.test(String(route.liquids || ""))) reasons.push("liquid forbidden");
  if (!dimensionsPass(route, input)) reasons.push("dimensions exceed route limit");

  const rate = parseRate(route.rateText);
  if (!rate) reasons.push("rate not parsed");

  return { ok: reasons.length === 0, reasons, rate };
}

export function shippingCost(route, input) {
  const status = routeStatus(route, input, Number(input.priceRub) || 0);
  if (!status.ok || !status.rate) return null;
  const weight = routeBillableWeight(route, input).billable;
  return status.rate.baseCny + status.rate.perGCny * weight;
}

export function commissionTierIndex(priceRub) {
  if (priceRub <= RUB_TIERS[0]) return 0;
  if (priceRub <= RUB_TIERS[1]) return 1;
  return 2;
}

export function etaMidpoint(etaDays) {
  const nums = String(etaDays || "").match(/\d+/g);
  if (!nums || !nums.length) return 99;
  if (nums.length === 1) return Number(nums[0]);
  return (Number(nums[0]) + Number(nums[1])) / 2;
}

export function rankRoutes(routes, strategy = "balanced") {
  if (!routes.length) return [];
  const costs = routes.map((route) => Number(route.costCny) || 0);
  const ratings = routes.map((route) => Number(route.ozonRating) || 99);
  const etas = routes.map((route) => etaMidpoint(route.etaDays));
  const norm = (value, values) => {
    const min = Math.min(...values);
    const max = Math.max(...values);
    return max === min ? 0 : (value - min) / (max - min);
  };
  const weighted = routes.map((route) => {
    const costScore = norm(Number(route.costCny) || 0, costs);
    const ratingScore = norm(Number(route.ozonRating) || 99, ratings);
    const etaScore = norm(etaMidpoint(route.etaDays), etas);
    const balancedScore = costScore * 0.5 + ratingScore * 0.3 + etaScore * 0.2;
    return {
      ...route,
      etaMidpoint: etaMidpoint(route.etaDays),
      balancedScore,
      scoreParts: { costScore, ratingScore, etaScore },
    };
  });
  if (strategy === "cost") {
    return weighted.sort((a, b) => a.costCny - b.costCny || Number(a.ozonRating || 99) - Number(b.ozonRating || 99));
  }
  if (strategy === "speed") {
    return weighted.sort((a, b) => a.etaMidpoint - b.etaMidpoint || a.costCny - b.costCny);
  }
  if (strategy === "rating") {
    return weighted.sort((a, b) => Number(a.ozonRating || 99) - Number(b.ozonRating || 99) || a.costCny - b.costCny);
  }
  return weighted.sort((a, b) => a.balancedScore - b.balancedScore || a.costCny - b.costCny);
}

export function buildDiagnostics(result, input) {
  const lines = [];
  if (!result.bestRoute) {
    lines.push({ level: "bad", text: "没有匹配线路：优先检查重量、货值、尺寸、电池/液体限制。" });
    return lines;
  }
  const shipPct = result.bestRoute.costCny / result.targetCny;
  if (shipPct > 0.35) {
    lines.push({ level: "warn", text: `物流占推荐价 ${(shipPct * 100).toFixed(0)}%，运费压力偏高。` });
  }
  if (result.targetRub > 1500 && result.targetRub <= 1700) {
    lines.push({ level: "warn", text: "售价刚超过 1500 RUB，可能从低价货值/佣金区间跳到下一档，建议试算降成本或调价。" });
  }
  if (result.availableRoutes.length < 5) {
    lines.push({ level: "warn", text: `可用线路只有 ${result.availableRoutes.length} 条，履约选择偏窄。` });
  }
  if (input.hasBattery || input.isLiquid) {
    lines.push({ level: "info", text: "带电/液体限制已参与线路筛选，建议优先看允许该属性的 3PL。" });
  }
  if (result.bestRoute.balancedScore !== undefined) {
    lines.push({
      level: "info",
      text: `平衡推荐权重：运费 50%，Ozon评分 30%，时效 20%；当前推荐 ${result.bestRoute.provider} ${result.bestRoute.serviceLevel}。`,
    });
  }
  if (!lines.length) {
    lines.push({ level: "good", text: "当前商品在线路、佣金和目标毛利上没有明显异常。" });
  }
  return lines.slice(0, 3);
}

export function costBreakdown(input, result) {
  if (!result || !result.bestRoute) return [];
  const targetCny = result.targetCny;
  const parts = [
    { key: "cost", label: "采购", value: Number(input.costCny) || 0, color: "#0069d9" },
    { key: "packing", label: "包装", value: Number(input.packingCny) || 0, color: "#7c3aed" },
    { key: "domestic", label: "国内运费", value: Number(input.domesticShipCny) || 0, color: "#0891b2" },
    { key: "other", label: "其他固定", value: Number(input.otherFixedCny) || 0, color: "#64748b" },
    { key: "shipping", label: "realFBS运费", value: result.bestRoute.costCny || 0, color: "#f97316" },
    { key: "commission", label: "Ozon佣金", value: targetCny * result.commission, color: "#dc2626" },
    { key: "payment", label: "支付费", value: targetCny * ((Number(input.paymentPct) || 0) / 100), color: "#9333ea" },
    { key: "ad", label: "广告", value: targetCny * ((Number(input.adPct) || 0) / 100), color: "#db2777" },
    { key: "return", label: "退货预留", value: targetCny * ((Number(input.returnReservePct) || 0) / 100), color: "#ca8a04" },
    { key: "loss", label: "损耗预留", value: targetCny * ((Number(input.lossReservePct) || 0) / 100), color: "#a16207" },
    { key: "profit", label: "利润", value: result.profitCny, color: result.profitCny >= 0 ? "#059669" : "#b42318" },
  ];
  const positiveTotal = parts.reduce((sum, part) => sum + Math.max(part.value, 0), 0) || 1;
  return parts
    .filter((part) => Math.abs(part.value) > 0.005)
    .map((part) => ({
      ...part,
      pctOfPrice: targetCny ? part.value / targetCny : 0,
      pctOfPositive: Math.max(part.value, 0) / positiveTotal,
    }));
}

export function solvePrice(input, routes, commissionCategory) {
  const rubCny = Number(input.rubCny) || 0.0927;
  const targetProfitOnCost = Math.max((Number(input.marginTargetPct) || 0) / 100, 0);
  const strategy = input.strategy || "balanced";
  const fixedBeforeShip =
    (Number(input.costCny) || 0) +
    (Number(input.domesticShipCny) || 0) +
    (Number(input.packingCny) || 0) +
    (Number(input.otherFixedCny) || 0);
  const ratioFees =
    (Number(input.paymentPct) || 0) / 100 +
    (Number(input.adPct) || 0) / 100 +
    (Number(input.returnReservePct) || 0) / 100 +
    (Number(input.lossReservePct) || 0) / 100;

  const candidates = [];
  routes.forEach((route) => {
    const rate = parseRate(route.rateText);
    if (!rate) return;
    const weight = routeBillableWeight(route, input).billable;
    const minW = Number(route.weightMinG) || 0;
    const maxW = Number(route.weightMaxG) || Infinity;
    if (weight < minW || weight > maxW) return;
    if (input.hasBattery && /forbidden|запрещено|禁止/i.test(String(route.batteries || ""))) return;
    if (input.isLiquid && /forbidden|запрещено|禁止/i.test(String(route.liquids || ""))) return;
    if (!dimensionsPass(route, input)) return;

    const shippingCny = rate.baseCny + rate.perGCny * weight;
    const costBaseCny = fixedBeforeShip + shippingCny;
    commissionCategory.rfbs.forEach((commission, tierIndex) => {
      const netCoef = 1 - commission - ratioFees;
      if (netCoef <= 0) return;
      const breakevenCny = costBaseCny / netCoef;
      const targetCny = (costBaseCny * (1 + targetProfitOnCost)) / netCoef;
      const targetRub = targetCny / rubCny;
      if (commissionTierIndex(targetRub) !== tierIndex) return;
      const status = routeStatus(route, input, targetRub);
      if (!status.ok) return;
      candidates.push({
        ...route,
        commission,
        tierIndex,
        billableWeightG: weight,
        costCny: shippingCny,
        costBaseCny,
        breakevenCny,
        targetCny,
        targetRub,
      });
    });
  });

  const availableRoutes = rankRoutes(candidates, strategy);
  const bestRoute = availableRoutes[0] || null;
  const shippingCny = bestRoute ? bestRoute.costCny : 0;
  const commission = bestRoute ? bestRoute.commission : commissionCategory.rfbs[0];
  const tierIndex = bestRoute ? bestRoute.tierIndex : 0;
  const netCoef = 1 - commission - ratioFees;
  if (netCoef <= 0) return null;
  const breakevenCny = (fixedBeforeShip + shippingCny) / netCoef;
  const costBaseCny = fixedBeforeShip + shippingCny;
  const targetCny = costBaseCny * (1 + targetProfitOnCost) / netCoef;
  const profitCny = targetCny * netCoef - fixedBeforeShip - shippingCny;

  const output = {
    commission,
    tierIndex,
    targetProfitOnCost: costBaseCny ? profitCny / costBaseCny : 0,
    costBaseCny,
    breakevenCny,
    targetCny,
    linePriceCny: targetCny / 0.8,
    linePriceRub: (targetCny / 0.8) / rubCny,
    targetRub: targetCny / rubCny,
    profitCny,
    margin: profitCny / targetCny,
    bestRoute,
    availableRoutes,
    chargeable: bestRoute ? routeBillableWeight(bestRoute, input) : chargeableWeight(input),
    diagnostics: [],
  };
  output.diagnostics = buildDiagnostics(output, input);
  output.costBreakdown = costBreakdown(input, output);
  return output;
}
