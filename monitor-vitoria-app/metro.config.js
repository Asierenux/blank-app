// En la vista previa web no existe el mapa nativo de Apple: se usa un sustituto sencillo.
const { getDefaultConfig } = require("expo/metro-config");
const path = require("path");

const config = getDefaultConfig(__dirname);
const original = config.resolver.resolveRequest;
config.resolver.resolveRequest = (context, moduleName, platform) => {
  if (platform === "web" && moduleName === "react-native-maps") {
    return { type: "sourceFile", filePath: path.join(__dirname, "web/mapa-web.tsx") };
  }
  return (original ?? context.resolveRequest)(context, moduleName, platform);
};
module.exports = config;
