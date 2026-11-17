window.onload = function () {
  window.ui = SwaggerUIBundle({
    url: "/openapi.json",
    dom_id: "#swagger-ui",
    deepLinking: true,
    // The online validator badge would send the address of the document to a third party.
    validatorUrl: null,
  });
};
