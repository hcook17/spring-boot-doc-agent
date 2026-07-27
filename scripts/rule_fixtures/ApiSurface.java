package com.example.fixtures;

import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiSurface {
    @GetMapping
    public String bare() { return "x"; }

    @PostMapping("/thing")
    public String withArgs() { return "x"; }

    @RequestMapping(value = "/legacy", method = RequestMethod.PUT)
    public String legacy() { return "x"; }
}

@Controller
class PlainController {
    @DeleteMapping("/gone")
    public void remove() { }
}
